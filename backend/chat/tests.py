from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from accounts import admin_services
from projects.models import Membership
from projects.services import create_project

from .models import Conversation, Message, Notification
from .services import parse_mentions

User = get_user_model()
PW = "pw-test-123"


class ChatCase(APITestCase):
    def setUp(self):
        cache.clear()  # la limite de débit (60 messages/min) est partagée entre les tests
        self.alice = User.objects.create_user("alice", password=PW)
        self.bob = User.objects.create_user("bob", password=PW)
        self.carol = User.objects.create_user("carol", password=PW)  # lectrice
        self.dave = User.objects.create_user("dave", password=PW)    # étranger
        self.team = create_project(self.alice, "Équipe")
        Membership.objects.create(project=self.team, user=self.bob, role="member")
        Membership.objects.create(project=self.team, user=self.carol, role="viewer")
        self.solo = create_project(self.alice, "Perso")

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def conv(self, user, project):
        rows = self.as_(user).get("/api/chat/conversations/").data
        return next(r for r in rows if r["project"] == project.pk)

    def say(self, user, conv_id, text):
        return self.as_(user).post(f"/api/chat/conversations/{conv_id}/messages/", {"content": text}, format="json")


class ConversationTests(ChatCase):
    def test_every_project_has_a_conversation_created_on_demand(self):
        rows = self.as_(self.alice).get("/api/chat/conversations/").data
        self.assertEqual(sorted(r["title"] for r in rows), ["Perso", "Équipe"])
        self.assertEqual(Conversation.objects.count(), 2)
        self.as_(self.alice).get("/api/chat/conversations/")
        self.assertEqual(Conversation.objects.count(), 2)  # pas de doublon

    def test_solo_project_is_a_notebook_and_team_project_is_not(self):
        self.assertTrue(self.conv(self.alice, self.solo)["solo"])
        team = self.conv(self.alice, self.team)
        self.assertFalse(team["solo"])
        self.assertEqual(sorted(m["username"] for m in team["members"]), ["alice", "bob", "carol"])

    def test_a_project_becomes_a_team_when_someone_joins(self):
        Membership.objects.create(project=self.solo, user=self.bob, role="member")
        self.assertFalse(self.conv(self.alice, self.solo)["solo"])

    def test_you_only_see_your_own_conversations(self):
        self.assertEqual(self.as_(self.dave).get("/api/chat/conversations/").data, [])

    def test_viewer_reads_but_cannot_write(self):
        c = self.conv(self.alice, self.team)
        self.say(self.alice, c["id"], "Bonjour")
        self.assertFalse(self.conv(self.carol, self.team)["can_write"])
        self.assertEqual(len(self.as_(self.carol).get(f"/api/chat/conversations/{c['id']}/messages/").data["messages"]), 1)
        self.assertEqual(self.say(self.carol, c["id"], "Salut").status_code, 403)

    def test_strangers_get_404_everywhere(self):
        c = self.conv(self.alice, self.team)
        m = self.say(self.alice, c["id"], "secret").data
        client = self.as_(self.dave)
        self.assertEqual(client.get(f"/api/chat/conversations/{c['id']}/messages/").status_code, 404)
        self.assertEqual(self.say(self.dave, c["id"], "x").status_code, 404)
        self.assertEqual(client.post(f"/api/chat/conversations/{c['id']}/read/").status_code, 404)
        self.assertEqual(client.delete(f"/api/chat/messages/{m['id']}/").status_code, 404)

    def test_unauthenticated_is_rejected(self):
        self.client.force_authenticate(None)
        for url in ("/api/chat/conversations/", "/api/chat/summary/", "/api/notifications/", "/api/chat/contacts/"):
            self.assertEqual(self.client.get(url).status_code, 401, url)


class MessageTests(ChatCase):
    def test_post_and_read_back_in_order(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.alice, c, "Un")
        self.say(self.bob, c, "Deux")
        data = self.as_(self.bob).get(f"/api/chat/conversations/{c}/messages/").data
        self.assertEqual([(m["author"]["username"], m["content"]) for m in data["messages"]], [("alice", "Un"), ("bob", "Deux")])
        self.assertFalse(data["has_more"])

    def test_empty_blank_and_too_long_messages_are_refused(self):
        c = self.conv(self.alice, self.team)["id"]
        for text in ("", "   \n ", None):
            self.assertEqual(self.say(self.alice, c, text).status_code, 400, repr(text))
        self.assertEqual(self.say(self.alice, c, "x" * 2001).status_code, 400)
        self.assertEqual(self.say(self.alice, c, "x" * 2000).status_code, 201)

    def test_html_is_stored_as_is_the_front_escapes_it(self):
        c = self.conv(self.alice, self.team)["id"]
        self.assertEqual(self.say(self.alice, c, "<script>alert(1)</script>").data["content"], "<script>alert(1)</script>")

    def test_pagination_latest_first_then_older_and_only_new(self):
        c = self.conv(self.alice, self.team)["id"]
        ids = [self.say(self.alice, c, f"m{i}").data["id"] for i in range(7)]
        url = f"/api/chat/conversations/{c}/messages/"
        page = self.as_(self.alice).get(url, {"limit": 3}).data
        self.assertEqual([m["content"] for m in page["messages"]], ["m4", "m5", "m6"])
        self.assertTrue(page["has_more"])
        older = self.as_(self.alice).get(url, {"limit": 3, "before": page["messages"][0]["id"]}).data
        self.assertEqual([m["content"] for m in older["messages"]], ["m1", "m2", "m3"])
        newer = self.as_(self.alice).get(url, {"after": ids[4]}).data
        self.assertEqual([m["content"] for m in newer["messages"]], ["m5", "m6"])
        self.assertEqual(self.as_(self.alice).get(url, {"after": "abc"}).status_code, 400)

    def test_author_deletes_own_message_but_not_others(self):
        c = self.conv(self.alice, self.team)["id"]
        mine, theirs = self.say(self.bob, c, "à moi").data, self.say(self.alice, c, "à elle").data
        self.assertTrue(mine["can_delete"])
        self.assertEqual(self.as_(self.bob).delete(f"/api/chat/messages/{theirs['id']}/").status_code, 403)
        self.assertEqual(self.as_(self.bob).delete(f"/api/chat/messages/{mine['id']}/").status_code, 204)

    def test_project_owner_moderates_any_message(self):
        c = self.conv(self.alice, self.team)["id"]
        m = self.say(self.bob, c, "hors sujet").data
        self.assertEqual(self.as_(self.alice).delete(f"/api/chat/messages/{m['id']}/").status_code, 204)
        self.assertFalse(Message.objects.exists())

    def test_deleting_a_message_removes_its_notification(self):
        c = self.conv(self.alice, self.team)["id"]
        m = self.say(self.alice, c, "@bob regarde").data
        self.assertEqual(Notification.objects.count(), 1)
        self.as_(self.alice).delete(f"/api/chat/messages/{m['id']}/")
        self.assertEqual(Notification.objects.count(), 0)


class MentionTests(ChatCase):
    def test_parsing_rules(self):
        people = [self.alice, self.bob, self.carol]
        names = lambda text, author=self.alice: sorted(u.username for u in parse_mentions(text, people, author)[0])
        self.assertEqual(names("salut @bob"), ["bob"])
        self.assertEqual(names("@BOB, tu peux voir ?"), ["bob"])          # casse ignorée, virgule ignorée
        self.assertEqual(names("@bob. Merci @carol!"), ["bob", "carol"])
        self.assertEqual(names("écris à jean@bob.fr"), [])                 # un email n'est pas une mention
        self.assertEqual(names("@inconnu"), [])
        self.assertEqual(names("@alice"), [])                              # on ne se notifie pas soi-même
        self.assertEqual(names("@bob @bob @bob"), ["bob"])                 # une seule notification
        self.assertEqual(names("@@bob"), [])

    def test_team_mention_notifies_only_the_mentioned_person(self):
        c = self.conv(self.alice, self.team)["id"]
        res = self.say(self.alice, c, "@bob peux-tu relire ?")
        self.assertEqual(res.data["mentions"], ["bob"])
        self.assertEqual(Notification.objects.get().user, self.bob)
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        self.assertEqual(self.as_(self.carol).get("/api/chat/summary/").data["unread_notifications"], 0)
        self.assertEqual(self.as_(self.alice).get("/api/chat/summary/").data["unread_notifications"], 0)

    def test_everyone_notifies_all_the_others(self):
        c = self.conv(self.alice, self.team)["id"]
        res = self.say(self.alice, c, "@tous réunion à 10 h")
        self.assertTrue(res.data["mentions_all"])
        self.assertEqual(sorted(n.user.username for n in Notification.objects.all()), ["bob", "carol"])
        self.assertEqual(self.say(self.alice, c, "@ALL again").data["mentions_all"], True)

    def test_you_cannot_mention_someone_outside_the_project(self):
        c = self.conv(self.alice, self.team)["id"]
        res = self.say(self.alice, c, "@dave viens voir")
        self.assertEqual((res.data["mentions"], Notification.objects.count()), ([], 0))

    def test_solo_notebook_notifies_nobody(self):
        c = self.conv(self.alice, self.solo)["id"]
        for text in ("@alice rappel", "@tous", "@bob"):
            self.assertEqual(self.say(self.alice, c, text).status_code, 201)
        self.assertEqual(Notification.objects.count(), 0)

    def test_notifications_listing_and_marking(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.alice, c, "@bob un")
        self.say(self.alice, c, "@bob deux")
        rows = self.as_(self.bob).get("/api/notifications/").data
        self.assertEqual([r["excerpt"] for r in rows], ["@bob deux", "@bob un"])  # récentes d'abord
        self.assertEqual((rows[0]["author"], rows[0]["conversation_title"], rows[0]["read"]), ("alice", "Équipe", False))
        self.as_(self.bob).post("/api/notifications/", {"ids": [rows[1]["id"]]}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        self.as_(self.bob).post("/api/notifications/", {"all": True}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 0)

    def test_opening_the_thread_marks_its_mentions_as_seen(self):
        team = self.conv(self.alice, self.team)["id"]
        self.say(self.alice, team, "@bob regarde")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        self.as_(self.bob).post(f"/api/chat/conversations/{team}/read/")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 0)

    def test_nobody_can_mark_someone_elses_notifications(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.alice, c, "@bob")
        n = self.as_(self.bob).get("/api/notifications/").data[0]["id"]
        self.as_(self.carol).post("/api/notifications/", {"ids": [n]}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        self.assertEqual(self.as_(self.carol).get("/api/notifications/").data, [])


class UnreadTests(ChatCase):
    def test_unread_counts_others_messages_until_read(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.alice, c, "1")
        self.say(self.alice, c, "2")
        self.assertEqual(self.conv(self.bob, self.team)["unread"], 2)
        self.assertEqual(self.conv(self.alice, self.team)["unread"], 0)  # ses propres messages ne comptent pas
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_messages"], 2)
        self.as_(self.bob).post(f"/api/chat/conversations/{c}/read/")
        self.assertEqual(self.conv(self.bob, self.team)["unread"], 0)
        self.say(self.alice, c, "3")
        self.assertEqual(self.conv(self.bob, self.team)["unread"], 1)
        self.say(self.bob, c, "4")  # répondre = avoir lu le fil
        self.assertEqual((self.conv(self.bob, self.team)["unread"], self.conv(self.alice, self.team)["unread"]), (0, 1))

    def test_posting_marks_your_own_thread_as_read(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.bob, c, "avant")
        self.say(self.alice, c, "ma réponse")
        self.assertEqual(self.conv(self.alice, self.team)["unread"], 0)

    def test_conversation_list_shows_last_message_and_active_first(self):
        self.say(self.alice, self.conv(self.alice, self.team)["id"], "ancien")
        self.say(self.alice, self.conv(self.alice, self.solo)["id"], "récent " + "mot " * 60)
        rows = self.as_(self.alice).get("/api/chat/conversations/").data
        self.assertEqual([r["title"] for r in rows], ["Perso", "Équipe"])
        self.assertTrue(rows[0]["last"]["excerpt"].endswith("…") and len(rows[0]["last"]["excerpt"]) <= 90)
        self.assertEqual(rows[1]["last"]["author"], "alice")


class DirectTests(ChatCase):
    def direct(self, user, other):
        return self.as_(user).post("/api/chat/direct/", {"user": other.pk if hasattr(other, "pk") else other}, format="json")

    def test_colleagues_can_talk_and_the_pair_is_unique_in_both_directions(self):
        a, b = self.direct(self.alice, self.bob), self.direct(self.bob, self.alice)
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(a.data["id"], b.data["id"])
        self.assertEqual((a.data["title"], b.data["title"]), ("bob", "alice"))
        self.assertEqual(self.direct(self.alice, "BOB").data["id"], a.data["id"])  # par nom aussi
        self.assertEqual(Conversation.objects.filter(kind="direct").count(), 1)

    def test_you_need_a_shared_project(self):
        self.assertEqual(self.direct(self.alice, self.dave).status_code, 404)
        self.assertEqual(self.direct(self.dave, self.alice).status_code, 404)
        unknown, stranger = self.direct(self.alice, "personne"), self.direct(self.alice, self.dave)
        self.assertEqual((unknown.status_code, unknown.data), (stranger.status_code, stranger.data))  # indiscernables

    def test_not_with_yourself_nor_an_inactive_account(self):
        self.assertEqual(self.direct(self.alice, self.alice).status_code, 400)
        self.bob.is_active = False
        self.bob.save()
        self.assertEqual(self.direct(self.alice, self.bob).status_code, 404)

    def test_a_viewer_can_still_chat_directly(self):
        self.assertEqual(self.direct(self.carol, self.alice).status_code, 200)

    def test_only_the_two_people_see_it(self):
        c = self.direct(self.alice, self.bob).data["id"]
        self.say(self.alice, c, "entre nous")
        self.assertEqual(self.as_(self.carol).get(f"/api/chat/conversations/{c}/messages/").status_code, 404)
        self.assertEqual(self.as_(self.dave).get(f"/api/chat/conversations/{c}/messages/").status_code, 404)
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_messages"], 1)

    def test_mentions_work_in_direct_but_everyone_does_not(self):
        c = self.direct(self.alice, self.bob).data["id"]
        self.assertEqual(self.say(self.alice, c, "@bob tu vois ?").data["mentions"], ["bob"])
        res = self.say(self.alice, c, "@tous")
        self.assertEqual((res.data["mentions_all"], res.data["mentions"]), (False, []))

    def test_only_the_author_deletes_in_direct(self):
        c = self.direct(self.alice, self.bob).data["id"]
        m = self.say(self.alice, c, "oups").data
        self.assertEqual(self.as_(self.bob).delete(f"/api/chat/messages/{m['id']}/").status_code, 403)
        self.assertEqual(self.as_(self.alice).delete(f"/api/chat/messages/{m['id']}/").status_code, 204)

    def test_contacts_are_the_people_sharing_a_project(self):
        self.assertEqual([u["username"] for u in self.as_(self.alice).get("/api/chat/contacts/").data], ["bob", "carol"])
        self.assertEqual([u["username"] for u in self.as_(self.bob).get("/api/chat/contacts/").data], ["alice", "carol"])
        self.assertEqual(self.as_(self.dave).get("/api/chat/contacts/").data, [])


class LifecycleTests(ChatCase):
    def test_deleting_a_project_deletes_its_conversation_and_messages(self):
        self.say(self.alice, self.conv(self.alice, self.team)["id"], "bye")
        self.team.delete()
        self.assertEqual(list(Conversation.objects.filter(kind="project").values_list("project", flat=True)), [self.solo.pk])
        self.assertEqual(Message.objects.count(), 0)

    def test_deleting_a_user_keeps_project_messages_signed_nobody_and_drops_direct_chats(self):
        c = self.conv(self.alice, self.team)["id"]
        self.say(self.bob, c, "je pars")
        d = self.as_(self.alice).post("/api/chat/direct/", {"user": self.bob.pk}, format="json").data["id"]
        self.say(self.bob, d, "en privé")
        root = User.objects.create_user("root", password=PW, is_staff=True)
        admin_services.delete_user(root, self.bob)
        self.assertIsNone(Message.objects.get(content="je pars").author)
        data = self.as_(self.alice).get(f"/api/chat/conversations/{c}/messages/").data["messages"]
        self.assertIsNone(data[0]["author"])
        self.assertFalse(Conversation.objects.filter(pk=d).exists())
