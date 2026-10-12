from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class AuthTests(APITestCase):
    def test_register_then_login_then_me(self):
        res = self.client.post(
            "/api/auth/register/", {"username": "alice", "email": "a@x.fr", "password": "Mot-de-passe-9"}
        )
        self.assertEqual(res.status_code, 201)
        self.assertNotIn("password", res.data)

        tok = self.client.post("/api/auth/token/", {"username": "alice", "password": "Mot-de-passe-9"})
        self.assertEqual(tok.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tok.data['access']}")
        me = self.client.get("/api/me/")
        self.assertEqual(me.data["username"], "alice")

    def test_weak_password_rejected(self):
        res = self.client.post("/api/auth/register/", {"username": "bob", "email": "b@x.fr", "password": "123"})
        self.assertEqual(res.status_code, 400)

    def test_duplicate_email_rejected(self):
        User.objects.create_user("alice", "a@x.fr", "Mot-de-passe-9")
        res = self.client.post(
            "/api/auth/register/", {"username": "alice2", "email": "A@x.fr", "password": "Mot-de-passe-9"}
        )
        self.assertEqual(res.status_code, 400)


from django.core.cache import cache
from django.test import override_settings

from projects.models import Membership
from projects.services import create_project


class ThrottleTests(APITestCase):
    def setUp(self):
        cache.clear()
        User.objects.create_user("alice", "a@x.fr", "Mot-de-passe-9")

    def tearDown(self):
        cache.clear()

    def login(self, password):
        return self.client.post("/api/auth/token/", {"username": "alice", "password": password})

    def test_login_is_limited_per_address_and_even_the_right_password_is_refused_after(self):
        codes = [self.login("mauvais").status_code for _ in range(10)]
        self.assertEqual(set(codes), {401})
        self.assertEqual(self.login("mauvais").status_code, 429)
        self.assertEqual(self.login("Mot-de-passe-9").status_code, 429)  # force brute : la bonne réponse ne passe plus non plus

    def test_a_normal_login_still_works(self):
        self.assertEqual(self.login("Mot-de-passe-9").status_code, 200)

    def test_registration_is_limited(self):
        codes = [self.client.post("/api/auth/register/", {"username": f"u{i}", "email": f"u{i}@x.fr", "password": "123"}).status_code for i in range(11)]
        self.assertEqual(codes[-1], 429)

    def test_chat_sending_is_limited_but_reading_is_not(self):
        alice = User.objects.get(username="alice")
        project = create_project(alice, "P")
        self.client.force_authenticate(alice)
        conv = self.client.get("/api/chat/conversations/").data[0]["id"]
        url = f"/api/chat/conversations/{conv}/messages/"
        codes = [self.client.post(url, {"content": f"m{i}"}, format="json").status_code for i in range(61)]
        self.assertEqual((codes[59], codes[60]), (201, 429))
        for _ in range(80):  # la relève des nouveaux messages ne doit jamais être freinée
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_changing_timezone_is_never_limited(self):
        self.client.force_authenticate(User.objects.get(username="alice"))
        for _ in range(15):
            self.assertEqual(self.client.patch("/api/me/", {"timezone": "Asia/Tokyo"}, format="json").status_code, 200)


class SelfServiceAccountTests(APITestCase):
    PW = "Mot-de-passe-9"

    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user("alice", "a@x.fr", self.PW)
        self.bob = User.objects.create_user("bob", "b@x.fr", self.PW)

    def tearDown(self):
        cache.clear()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def test_export_contains_my_data_and_nobody_elses(self):
        from tasks.models import Task
        p = create_project(self.alice, "Site")
        Task.objects.create(project=p, title="Maquette", assignee=self.alice)
        other = create_project(self.bob, "Secret")
        Task.objects.create(project=other, title="Confidentiel", assignee=self.bob)
        res = self.as_(self.alice).get("/api/me/export/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("attachment", res["Content-Disposition"])
        self.assertEqual(res.data["account"]["username"], "alice")
        self.assertEqual([t["title"] for t in res.data["tasks_assigned"]], ["Maquette"])
        dump = str(res.data)
        self.assertNotIn("Confidentiel", dump)
        self.assertNotIn("password", dump.lower())

    def test_export_requires_authentication(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/me/export/").status_code, 401)

    def test_delete_needs_the_right_password(self):
        self.assertEqual(self.as_(self.alice).delete("/api/me/", {"password": "faux"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.alice).delete("/api/me/", {}, format="json").status_code, 400)
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_delete_removes_the_account_and_solo_projects_but_keeps_shared_content_signed_nobody(self):
        from chat.models import Message
        from chat.services import post_message, project_conversation
        from tasks.models import Comment, Task
        solo = create_project(self.alice, "Perso")
        team = create_project(self.bob, "Équipe")
        Membership.objects.create(project=team, user=self.alice, role="member")
        task = Task.objects.create(project=team, title="T", assignee=self.alice)
        Comment.objects.create(task=task, author=self.alice, content="avis")
        post_message(self.alice, project_conversation(self.bob, team), "bonjour")
        res = self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json")
        self.assertEqual(res.status_code, 204)
        self.assertFalse(User.objects.filter(username="alice").exists())
        self.assertFalse(solo.__class__.objects.filter(pk=solo.pk).exists())
        self.assertTrue(team.__class__.objects.filter(pk=team.pk).exists())
        self.assertIsNone(Message.objects.get(content="bonjour").author)
        self.assertIsNone(Comment.objects.get(content="avis").author)
        Task.objects.get(pk=task.pk)  # la tâche reste, non assignée
        self.assertIsNone(Task.objects.get(pk=task.pk).assignee)

    def test_cannot_delete_while_owning_a_shared_project(self):
        p = create_project(self.alice, "Équipe")
        Membership.objects.create(project=p, user=self.bob, role="member")
        res = self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Équipe", str(res.data))
        self.assertTrue(User.objects.filter(username="alice").exists())

    def test_after_transferring_ownership_deletion_works(self):
        p = create_project(self.alice, "Équipe")
        Membership.objects.create(project=p, user=self.bob, role="member")
        self.assertEqual(self.as_(self.alice).post(f"/api/projects/{p.pk}/transfer/", {"user_id": self.bob.pk}, format="json").status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.owner, self.bob)
        self.assertEqual(self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json").status_code, 204)

    def test_only_the_owner_can_transfer_and_only_to_a_member(self):
        p = create_project(self.alice, "Équipe")
        Membership.objects.create(project=p, user=self.bob, role="member")
        carol = User.objects.create_user("carol", "c@x.fr", self.PW)
        self.assertEqual(self.as_(self.bob).post(f"/api/projects/{p.pk}/transfer/", {"user_id": self.bob.pk}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.alice).post(f"/api/projects/{p.pk}/transfer/", {"user_id": carol.pk}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.alice).post(f"/api/projects/{p.pk}/transfer/", {"user_id": self.alice.pk}, format="json").status_code, 400)
        self.assertEqual(self.as_(carol).post(f"/api/projects/{p.pk}/transfer/", {"user_id": carol.pk}, format="json").status_code, 404)

    def test_last_active_admin_cannot_delete_themselves(self):
        self.alice.is_staff = True
        self.alice.save()
        res = self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertIn("dernier administrateur", str(res.data))
        self.bob.is_staff = True
        self.bob.save()
        self.assertEqual(self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json").status_code, 204)

    def test_deletion_is_audited_without_secrets(self):
        from .models import AuditLog
        self.as_(self.alice).delete("/api/me/", {"password": self.PW}, format="json")
        row = AuditLog.objects.get(action="user.self_delete")
        self.assertEqual((row.actor_name, row.target), ("alice", "alice"))
        self.assertNotIn(self.PW, str(row.details))

    def test_deletion_attempts_are_rate_limited(self):
        codes = [self.as_(self.alice).delete("/api/me/", {"password": "faux"}, format="json").status_code for _ in range(11)]
        self.assertEqual(codes[-1], 429)
