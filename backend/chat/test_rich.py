import io
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from projects.models import Membership
from tasks.models import Task

from .models import Attachment, Message, Notification, Reaction
from .tests import ChatCase

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n" + b"x" * 50


def upload(name, data, ctype="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=ctype)


class EditAndReplyTests(ChatCase):
    def conv_id(self, user=None):
        return self.conv(user or self.alice, self.team)["id"]

    def test_author_edits_and_the_message_is_flagged_edited(self):
        c = self.conv_id()
        m = self.say(self.alice, c, "Bonjour").data
        self.assertFalse(m["edited"])
        res = self.as_(self.alice).patch(f"/api/chat/messages/{m['id']}/", {"content": "Bonjour à tous"}, format="json")
        self.assertEqual((res.status_code, res.data["content"], res.data["edited"]), (200, "Bonjour à tous", True))

    def test_nobody_else_edits_not_even_the_project_owner(self):
        c = self.conv_id()
        m = self.say(self.bob, c, "avis").data
        for user in (self.alice, self.carol):
            self.assertEqual(self.as_(user).patch(f"/api/chat/messages/{m['id']}/", {"content": "x"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.dave).patch(f"/api/chat/messages/{m['id']}/", {"content": "x"}, format="json").status_code, 404)

    def test_editing_validates_like_posting(self):
        c = self.conv_id()
        m = self.say(self.alice, c, "ok").data
        for bad in ("", "   ", "x" * 2001):
            self.assertEqual(self.as_(self.alice).patch(f"/api/chat/messages/{m['id']}/", {"content": bad}, format="json").status_code, 400)

    def test_editing_notifies_only_newly_mentioned_people(self):
        c = self.conv_id()
        m = self.say(self.alice, c, "@bob regarde").data
        self.as_(self.alice).patch(f"/api/chat/messages/{m['id']}/", {"content": "@bob @carol regardez"}, format="json")
        self.assertEqual(sorted(n.user.username for n in Notification.objects.all()), ["bob", "carol"])  # bob une seule fois
        self.assertEqual(Message.objects.get(pk=m["id"]).mentions.count(), 2)

    def test_reply_shows_the_quoted_message_and_stays_in_the_thread(self):
        c = self.conv_id()
        first = self.say(self.alice, c, "Qui s'occupe des photos ?").data
        res = self.as_(self.bob).post(f"/api/chat/conversations/{c}/messages/", {"content": "Moi !", "reply_to": first["id"]}, format="json")
        self.assertEqual(res.data["reply_to"], {"id": first["id"], "author": "alice", "excerpt": "Qui s'occupe des photos ?"})

    def test_reply_to_a_message_of_another_conversation_is_refused(self):
        other = self.say(self.alice, self.conv(self.alice, self.solo)["id"], "perso").data
        res = self.as_(self.alice).post(f"/api/chat/conversations/{self.conv_id()}/messages/", {"content": "x", "reply_to": other["id"]}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_deleting_the_quoted_message_keeps_the_reply(self):
        c = self.conv_id()
        first = self.say(self.alice, c, "à supprimer").data
        reply = self.as_(self.bob).post(f"/api/chat/conversations/{c}/messages/", {"content": "réponse", "reply_to": first["id"]}, format="json").data
        self.as_(self.alice).delete(f"/api/chat/messages/{first['id']}/")
        data = self.as_(self.bob).get(f"/api/chat/conversations/{c}/messages/").data["messages"]
        self.assertEqual((data[0]["content"], data[0]["reply_to"]), ("réponse", None))


class ReactionTests(ChatCase):
    def test_toggle_a_reaction_on_and_off_and_count_by_emoji(self):
        c = self.conv(self.alice, self.team)["id"]
        m = self.say(self.alice, c, "super").data
        url = f"/api/chat/messages/{m['id']}/reactions/"
        r = self.as_(self.bob).post(url, {"emoji": "👍"}, format="json").data
        self.assertEqual(r["reactions"], [{"emoji": "👍", "count": 1, "mine": True, "users": ["bob"]}])
        r = self.as_(self.alice).post(url, {"emoji": "👍"}, format="json").data
        self.assertEqual((r["reactions"][0]["count"], r["reactions"][0]["mine"]), (2, True))
        r = self.as_(self.bob).post(url, {"emoji": "👍"}, format="json").data
        self.assertEqual((r["reactions"][0]["count"], r["reactions"][0]["mine"]), (1, False))
        self.as_(self.alice).post(url, {"emoji": "👍"}, format="json")
        self.assertEqual(Reaction.objects.count(), 0)

    def test_only_the_proposed_emojis_are_accepted(self):
        m = self.say(self.alice, self.conv(self.alice, self.team)["id"], "x").data
        for bad in ("💩", "<script>", "", None):
            self.assertEqual(self.as_(self.bob).post(f"/api/chat/messages/{m['id']}/reactions/", {"emoji": bad}, format="json").status_code, 400)

    def test_viewer_and_stranger_cannot_react(self):
        m = self.say(self.alice, self.conv(self.alice, self.team)["id"], "x").data
        url = f"/api/chat/messages/{m['id']}/reactions/"
        self.assertEqual(self.as_(self.carol).post(url, {"emoji": "👍"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.dave).post(url, {"emoji": "👍"}, format="json").status_code, 404)


class TaskReferenceTests(ChatCase):
    def test_hash_number_links_a_task_of_the_same_project(self):
        t = Task.objects.create(project=self.team, title="Maquettes")
        c = self.conv(self.alice, self.team)["id"]
        m = self.say(self.alice, c, f"voir #{t.pk} et #99999 et #{t.pk}").data
        self.assertEqual(m["tasks"], [{"id": t.pk, "title": "Maquettes", "status": "todo", "project": self.team.pk}])

    def test_a_task_of_another_project_is_never_exposed(self):
        secret = Task.objects.create(project=self.solo, title="Confidentiel")
        m = self.say(self.alice, self.conv(self.alice, self.team)["id"], f"#{secret.pk}").data
        self.assertEqual(m["tasks"], [])
        self.assertNotIn("Confidentiel", str(m))

    def test_no_task_links_in_direct_conversations(self):
        t = Task.objects.create(project=self.team, title="Maquettes")
        d = self.as_(self.alice).post("/api/chat/direct/", {"user": self.bob.pk}, format="json").data["id"]
        self.assertEqual(self.say(self.alice, d, f"#{t.pk}").data["tasks"], [])

    def test_html_entities_are_not_task_references(self):
        t = Task.objects.create(project=self.team, title="X")
        self.assertEqual(self.say(self.alice, self.conv(self.alice, self.team)["id"], f"&#{t.pk};").data["tasks"], [])


class SearchTests(ChatCase):
    def test_finds_messages_only_in_my_conversations_newest_first(self):
        a = self.say(self.alice, self.conv(self.alice, self.team)["id"], "Le budget du site").data
        b = self.say(self.bob, self.conv(self.bob, self.team)["id"], "budget validé").data
        self.say(self.alice, self.conv(self.alice, self.solo)["id"], "mon budget perso").data
        rows = self.as_(self.bob).get("/api/chat/search/", {"q": "BUDGET"}).data
        self.assertEqual([r["message"] for r in rows], [b["id"], a["id"]])
        self.assertEqual(rows[0]["conversation_title"], "Équipe")
        self.assertEqual(self.as_(self.dave).get("/api/chat/search/", {"q": "budget"}).data, [])

    def test_a_viewer_can_search_and_a_direct_chat_is_private(self):
        d = self.as_(self.alice).post("/api/chat/direct/", {"user": self.bob.pk}, format="json").data["id"]
        self.say(self.alice, d, "mot-secret")
        self.assertEqual(len(self.as_(self.bob).get("/api/chat/search/", {"q": "mot-secret"}).data), 1)
        self.assertEqual(self.as_(self.carol).get("/api/chat/search/", {"q": "mot-secret"}).data, [])

    def test_short_queries_are_refused(self):
        self.assertEqual(self.as_(self.alice).get("/api/chat/search/", {"q": "a"}).status_code, 400)
        self.assertEqual(self.as_(self.alice).get("/api/chat/search/").status_code, 400)

    def test_around_returns_the_hit_with_its_context(self):
        c = self.conv(self.alice, self.team)["id"]
        ids = [self.say(self.alice, c, f"m{i}").data["id"] for i in range(30)]
        data = self.as_(self.alice).get(f"/api/chat/conversations/{c}/messages/", {"around": ids[25]}).data
        got = [m["content"] for m in data["messages"]]
        self.assertIn("m25", got)
        self.assertEqual((got[0], got[-1]), ("m6", "m29"))
        self.assertTrue(data["has_more"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="taskflow-test-media-"))
class AttachmentTests(ChatCase):
    def send(self, user, files, content="", conv=None):
        c = conv or self.conv(user, self.team)["id"]
        return self.as_(user).post(f"/api/chat/conversations/{c}/messages/", {"content": content, "files": files}, format="multipart")

    def test_an_image_can_be_sent_and_downloaded_by_participants_only(self):
        res = self.send(self.alice, [upload("photo.png", PNG)], "Voici")
        self.assertEqual(res.status_code, 201, res.data)
        att = res.data["attachments"][0]
        self.assertEqual((att["name"], att["image"], att["content_type"]), ("photo.png", True, "image/png"))
        got = self.as_(self.bob).get(f"/api/chat/attachments/{att['id']}/")
        self.assertEqual((got.status_code, got["Content-Type"]), (200, "image/png"))
        self.assertEqual(b"".join(got.streaming_content), PNG)
        self.assertEqual(got["X-Content-Type-Options"], "nosniff")
        self.assertIn("sandbox", got["Content-Security-Policy"])
        self.assertEqual(self.as_(self.carol).get(f"/api/chat/attachments/{att['id']}/").status_code, 200)  # lecteur : peut lire
        self.assertEqual(self.as_(self.dave).get(f"/api/chat/attachments/{att['id']}/").status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/chat/attachments/{att['id']}/").status_code, 401)

    def test_a_pdf_is_a_download_not_displayed_inline(self):
        att = self.send(self.alice, [upload("devis.pdf", PDF)]).data["attachments"][0]
        got = self.as_(self.bob).get(f"/api/chat/attachments/{att['id']}/")
        self.assertIn("attachment", got["Content-Disposition"])
        self.assertIn("devis.pdf", got["Content-Disposition"])

    def test_a_file_alone_is_a_valid_message(self):
        self.assertEqual(self.send(self.alice, [upload("a.png", PNG)]).status_code, 201)

    def test_dangerous_types_are_refused_whatever_the_browser_says(self):
        for name, data in (("virus.exe", b"MZ\x90\x00"), ("page.html", b"<script>alert(1)</script>"), ("logo.svg", b"<svg onload=alert(1)>"),
                           ("script.js", b"alert(1)"), ("noext", b"abc"), ("double.png.exe", b"MZ")):
            res = self.send(self.alice, [upload(name, data, "image/png")])
            self.assertEqual(res.status_code, 400, name)
        self.assertEqual(Attachment.objects.count(), 0)

    def test_the_content_must_match_the_extension(self):
        self.assertEqual(self.send(self.alice, [upload("fake.png", b"<html>pas une image</html>", "image/png")]).status_code, 400)
        self.assertEqual(self.send(self.alice, [upload("fake.pdf", PNG)]).status_code, 400)
        self.assertEqual(self.send(self.alice, [upload("vide.png", b"")]).status_code, 400)
        self.assertEqual(self.send(self.alice, [upload("bin.txt", b"abc\x00def")]).status_code, 400)

    def test_size_and_count_limits(self):
        self.assertEqual(self.send(self.alice, [upload("gros.png", PNG + b"\x00" * (5 * 1024 * 1024))]).status_code, 400)
        four = [upload(f"{i}.png", PNG) for i in range(4)]
        self.assertEqual(self.send(self.alice, four).status_code, 400)
        self.assertEqual(self.send(self.alice, [upload(f"{i}.png", PNG) for i in range(3)]).status_code, 201)

    def test_the_original_name_never_reaches_the_file_system(self):
        att = self.send(self.alice, [upload("../../etc/passwd.png", PNG)]).data["attachments"][0]
        self.assertEqual(att["name"], "passwd.png")
        stored = Attachment.objects.get(pk=att["id"]).file.name
        self.assertTrue(stored.startswith("chat/") and ".." not in stored and "passwd" not in stored)

    def test_viewer_cannot_upload(self):
        self.assertEqual(self.send(self.carol, [upload("a.png", PNG)]).status_code, 403)

    def test_deleting_the_message_deletes_the_file(self):
        res = self.send(self.alice, [upload("a.png", PNG)]).data
        path = Attachment.objects.get().file.path
        import os
        self.assertTrue(os.path.exists(path))
        self.as_(self.alice).delete(f"/api/chat/messages/{res['id']}/")
        self.assertFalse(os.path.exists(path))
