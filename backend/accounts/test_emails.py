from datetime import date, datetime, timedelta
from io import StringIO
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounts.emails import build_digest
from accounts.models import Profile
from agenda.models import Event, Invitation
from projects.models import Membership
from projects.services import create_project
from tasks.models import Task

User = get_user_model()
PW = "pw-test-123"


class EmailCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user("alice", "alice@x.fr", PW)
        self.bob = User.objects.create_user("bob", "bob@x.fr", PW)
        self.team = create_project(self.alice, "Équipe")
        Membership.objects.create(project=self.team, user=self.bob, role="member")

    def tearDown(self):
        cache.clear()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def say(self, user, text):
        conv = next(c for c in self.as_(user).get("/api/chat/conversations/").data if c["project"] == self.team.pk)["id"]
        with self.captureOnCommitCallbacks(execute=True):
            return self.as_(user).post(f"/api/chat/conversations/{conv}/messages/", {"content": text}, format="json")


class MentionEmailTests(EmailCase):
    def test_a_mention_sends_one_email_to_the_mentioned_person_only(self):
        self.say(self.alice, "@bob peux-tu relire le CDC ?")
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        self.assertEqual(m.to, ["bob@x.fr"])
        self.assertIn("alice vous a mentionné dans « Équipe »", m.subject)
        self.assertIn("relire le CDC", m.body)
        self.assertIn("http", m.body)

    def test_no_email_without_a_mention_and_none_to_the_author(self):
        self.say(self.alice, "bonjour tout le monde")
        self.say(self.alice, "@alice note à moi-même")
        self.assertEqual(mail.outbox, [])

    def test_everyone_mentions_email_everyone_else(self):
        carol = User.objects.create_user("carol", "carol@x.fr", PW)
        Membership.objects.create(project=self.team, user=carol, role="viewer")
        self.say(self.alice, "@tous réunion demain")
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["bob@x.fr", "carol@x.fr"])

    def test_the_preference_is_respected(self):
        self.as_(self.bob).patch("/api/me/", {"notify_email": False}, format="json")
        self.say(self.alice, "@bob salut")
        self.assertEqual(mail.outbox, [])
        self.assertEqual(Profile.objects.get(user=self.bob).notify_email, False)

    def test_at_most_one_mention_email_per_thread_every_ten_minutes(self):
        self.say(self.alice, "@bob un")
        self.say(self.alice, "@bob deux")
        self.assertEqual(len(mail.outbox), 1)
        cache.clear()
        self.say(self.alice, "@bob trois")
        self.assertEqual(len(mail.outbox), 2)

    def test_editing_a_message_does_not_resend_to_the_same_person(self):
        res = self.say(self.alice, "@bob regarde")
        cache.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.as_(self.alice).patch(f"/api/chat/messages/{res.data['id']}/", {"content": "@bob regarde bien"}, format="json")
        self.assertEqual(len(mail.outbox), 1)

    def test_a_user_without_email_or_inactive_is_skipped_silently(self):
        self.bob.email = ""
        self.bob.save()
        self.say(self.alice, "@bob salut")
        self.assertEqual(mail.outbox, [])

    def test_a_mail_server_failure_never_blocks_the_message(self):
        with mock.patch("accounts.emails.send_mail", side_effect=OSError("SMTP down")), self.assertLogs("accounts.emails", "ERROR"):
            res = self.say(self.alice, "@bob salut")
        self.assertEqual(res.status_code, 201)

    def test_the_email_never_contains_html_injection_or_secrets(self):
        self.say(self.alice, "@bob <script>alert(1)</script>")
        self.assertNotIn(PW, mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].content_subtype, "plain")  # texte brut : rien n'est interprété


class InvitationEmailTests(EmailCase):
    def test_an_invitation_sends_an_email_with_the_time_in_the_guests_timezone(self):
        Profile.objects.update_or_create(user=self.bob, defaults={"timezone": "Asia/Tokyo"})
        with self.captureOnCommitCallbacks(execute=True):
            res = self.as_(self.alice).post("/api/events/", {"title": "Point", "starts_at": "2026-10-14T10:00", "ends_at": "2026-10-14T11:00",
                                                           "attendees": [self.bob.pk]}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("14/10/2026 à 17:00", mail.outbox[0].body)  # 10 h à Paris (UTC+2) = 17 h à Tokyo
        self.assertIn("Asia/Tokyo", mail.outbox[0].body)

    def test_updating_an_event_does_not_re_email_existing_guests(self):
        with self.captureOnCommitCallbacks(execute=True):
            e = self.as_(self.alice).post("/api/events/", {"title": "P", "starts_at": "2026-10-14T10:00", "ends_at": "2026-10-14T11:00",
                                                         "attendees": [self.bob.pk]}, format="json").data
        with self.captureOnCommitCallbacks(execute=True):
            self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"title": "Renommé", "attendees": [self.bob.pk]}, format="json")
        self.assertEqual(len(mail.outbox), 1)


class DigestTests(EmailCase):
    def setUp(self):
        super().setUp()
        self.today = datetime.now(ZoneInfo("Europe/Paris")).date()

    def test_nothing_to_say_means_no_email(self):
        self.assertIsNone(build_digest(self.bob))

    def test_the_digest_lists_events_due_and_late_tasks(self):
        Task.objects.create(project=self.team, title="Maquettes", assignee=self.bob, due_date=self.today)
        Task.objects.create(project=self.team, title="Contenus", assignee=self.bob, due_date=self.today - timedelta(days=3))
        Task.objects.create(project=self.team, title="Terminée", assignee=self.bob, due_date=self.today, status="done")
        Task.objects.create(project=self.team, title="Autre personne", assignee=self.alice, due_date=self.today)
        start = datetime(self.today.year, self.today.month, self.today.day, 14, 30, tzinfo=ZoneInfo("Europe/Paris"))
        Event.objects.create(project=self.team, creator=self.alice, title="Revue", starts_at=start, ends_at=start + timedelta(hours=1), timezone="Europe/Paris")
        body = build_digest(self.bob)
        self.assertIn("14:30  Revue", body)
        self.assertIn("• Maquettes (Équipe)", body)
        self.assertIn("En retard", body)
        self.assertIn("• Contenus", body)
        self.assertNotIn("Terminée", body)
        self.assertNotIn("Autre personne", body)

    def test_events_of_other_days_and_declined_invitations_are_left_out(self):
        tomorrow = datetime(self.today.year, self.today.month, self.today.day, 10, tzinfo=ZoneInfo("Europe/Paris")) + timedelta(days=1)
        Event.objects.create(project=self.team, creator=self.alice, title="Demain", starts_at=tomorrow, ends_at=tomorrow + timedelta(hours=1))
        now = datetime.combine(self.today, datetime.min.time().replace(hour=16), tzinfo=ZoneInfo("Europe/Paris"))
        refused = Event.objects.create(project=self.team, creator=self.alice, title="Refusé", starts_at=now, ends_at=now + timedelta(hours=1))
        Invitation.objects.create(event=refused, user=self.bob, status="declined")
        Task.objects.create(project=self.team, title="Pour que le résumé existe", assignee=self.bob, due_date=self.today)
        body = build_digest(self.bob)
        self.assertNotIn("Demain", body)
        self.assertNotIn("Refusé", body)

    def test_a_recurring_event_appears_today(self):
        start = datetime(2026, 1, 5, 9, 0, tzinfo=ZoneInfo("Europe/Paris"))
        Event.objects.create(project=self.team, creator=self.alice, title="Point quotidien", starts_at=start, ends_at=start + timedelta(minutes=15),
                             timezone="Europe/Paris", recurrence="daily")
        self.assertIn("09:00  Point quotidien", build_digest(self.bob))

    def test_the_command_only_writes_to_people_who_opted_in(self):
        Task.objects.create(project=self.team, title="À faire", assignee=self.bob, due_date=self.today)
        Task.objects.create(project=self.team, title="À faire aussi", assignee=self.alice, due_date=self.today)
        call_command("send_digest", stdout=StringIO())
        self.assertEqual(mail.outbox, [])  # personne n'a activé le résumé
        Profile.for_user(self.bob)
        Profile.objects.filter(user=self.bob).update(digest_email=True)
        out = StringIO()
        call_command("send_digest", stdout=out)
        self.assertEqual([m.to for m in mail.outbox], [["bob@x.fr"]])
        self.assertIn("À faire", mail.outbox[0].body)
        self.assertNotIn("À faire aussi", mail.outbox[0].body)
        self.assertIn("1 résumé(s) envoyé(s)", out.getvalue())

    def test_dry_run_prints_without_sending(self):
        Task.objects.create(project=self.team, title="À faire", assignee=self.bob, due_date=self.today)
        Profile.for_user(self.bob)
        Profile.objects.filter(user=self.bob).update(digest_email=True)
        out = StringIO()
        call_command("send_digest", "--dry-run", stdout=out)
        self.assertEqual(mail.outbox, [])
        self.assertIn("bob@x.fr", out.getvalue())

    def test_preferences_can_be_changed_through_the_api(self):
        res = self.as_(self.bob).patch("/api/me/", {"digest_email": True, "notify_email": False}, format="json")
        self.assertEqual((res.data["digest_email"], res.data["notify_email"]), (True, False))
