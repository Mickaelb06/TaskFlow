
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import AuditLog, SiteSettings
from projects.models import Membership, Project
from projects.services import create_project
from tasks.models import Comment, Task

User = get_user_model()
PW = "Mot-de-passe-Solide-9"


class AdminBase(APITestCase):
    def setUp(self):
        self.root = User.objects.create_user("root", "root@x.fr", PW, is_staff=True, is_superuser=True)
        self.admin = User.objects.create_user("admin", "admin@x.fr", PW, is_staff=True)
        self.alice = User.objects.create_user("alice", "alice@x.fr", PW)
        self.bob = User.objects.create_user("bob", "bob@x.fr", PW)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def actions(self):
        return list(AuditLog.objects.order_by("id").values_list("action", flat=True))


class AdminAccessTests(AdminBase):
    ENDPOINTS = ["stats/", "users/", "users/1/", "projects/", "audit/", "settings/"]

    def test_anonymous_gets_401_and_normal_user_403_everywhere(self):
        for path in self.ENDPOINTS:
            self.assertEqual(self.client.get(f"/api/admin/{path}").status_code, 401, path)
        self.as_(self.alice)
        for path in self.ENDPOINTS:
            self.assertEqual(self.client.get(f"/api/admin/{path}").status_code, 403, path)
        self.assertEqual(self.client.post("/api/admin/users/", {"username": "x", "email": "x@x.fr"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/admin/users/{self.bob.pk}/").status_code, 403)
        self.assertEqual(self.client.patch("/api/admin/settings/", {"allow_registration": False}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.bob.pk).exists())

    def test_a_deactivated_admin_loses_access(self):
        self.admin.is_active = False
        self.admin.save()
        self.as_(self.admin)
        self.assertIn(self.client.get("/api/admin/users/").status_code, (401, 403))

    def test_me_exposes_is_staff(self):
        self.assertTrue(self.as_(self.admin).get("/api/me/").data["is_staff"])
        self.assertFalse(self.as_(self.alice).get("/api/me/").data["is_staff"])


class AdminUserTests(AdminBase):
    def test_list_search_and_filters(self):
        self.as_(self.admin)
        self.assertEqual(len(self.client.get("/api/admin/users/").data), 4)
        self.assertEqual([u["username"] for u in self.client.get("/api/admin/users/", {"q": "ali"}).data], ["alice"])
        self.assertEqual({u["username"] for u in self.client.get("/api/admin/users/", {"filter": "admin"}).data}, {"root", "admin"})
        self.bob.is_active = False
        self.bob.save()
        self.assertEqual([u["username"] for u in self.client.get("/api/admin/users/", {"filter": "inactive"}).data], ["bob"])

    def test_list_counts_projects_and_open_tasks(self):
        p = create_project(self.alice, "P")
        Task.objects.create(project=p, title="a", assignee=self.alice)
        Task.objects.create(project=p, title="b", assignee=self.alice, status="done")
        row = [u for u in self.as_(self.admin).get("/api/admin/users/").data if u["username"] == "alice"][0]
        self.assertEqual((row["project_count"], row["owned_count"], row["open_tasks"]), (1, 1, 1))

    def test_create_user_with_chosen_password_can_log_in(self):
        res = self.as_(self.admin).post("/api/admin/users/", {"username": "carol", "email": "carol@x.fr", "password": PW})
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(res.data["generated_password"])
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "carol", "password": PW}).status_code, 200)

    def test_create_user_generates_password_shown_once(self):
        res = self.as_(self.admin).post("/api/admin/users/", {"username": "dan", "email": "dan@x.fr", "is_staff": True})
        self.assertEqual(res.status_code, 201)
        pwd = res.data["generated_password"]
        self.assertGreaterEqual(len(pwd), 10)
        self.assertTrue(User.objects.get(username="dan").is_staff)
        self.assertEqual(self.client.get(f"/api/admin/users/{res.data['id']}/").data.get("generated_password"), None)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "dan", "password": pwd}).status_code, 200)

    def test_create_user_validation(self):
        c = self.as_(self.admin)
        self.assertEqual(c.post("/api/admin/users/", {"username": "ALICE", "email": "n@x.fr"}).status_code, 400)
        self.assertEqual(c.post("/api/admin/users/", {"username": "n", "email": "ALICE@x.fr"}).status_code, 400)
        self.assertEqual(c.post("/api/admin/users/", {"username": "n", "email": "n@x.fr", "password": "123"}).status_code, 400)
        self.assertEqual(c.post("/api/admin/users/", {"username": "bad name!", "email": "n@x.fr"}).status_code, 400)
        self.assertEqual(c.post("/api/admin/users/", {"username": "n", "email": "pas-un-email"}).status_code, 400)

    def test_cannot_create_superuser_through_the_api(self):
        c = self.as_(self.admin)
        res = c.post("/api/admin/users/", {"username": "n", "email": "n@x.fr", "is_superuser": True})
        self.assertEqual(res.status_code, 201)
        self.assertFalse(User.objects.get(username="n").is_superuser)

    def test_deactivated_user_cannot_log_in_nor_use_an_existing_token(self):
        self.client.force_authenticate(None)
        access = self.client.post("/api/auth/token/", {"username": "alice", "password": PW}).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/me/").status_code, 200)
        self.as_(self.admin).patch(f"/api/admin/users/{self.alice.pk}/", {"is_active": False})
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "alice", "password": PW}).status_code, 401)
        self.as_(self.admin).patch(f"/api/admin/users/{self.alice.pk}/", {"is_active": True})
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "alice", "password": PW}).status_code, 200)

    def test_update_email_promote_demote(self):
        c = self.as_(self.admin)
        self.assertEqual(c.patch(f"/api/admin/users/{self.bob.pk}/", {"email": "new@x.fr"}).data["email"], "new@x.fr")
        self.assertEqual(c.patch(f"/api/admin/users/{self.bob.pk}/", {"email": "alice@x.fr"}).status_code, 400)
        self.assertTrue(c.patch(f"/api/admin/users/{self.bob.pk}/", {"is_staff": True}).data["is_staff"])
        self.assertFalse(c.patch(f"/api/admin/users/{self.bob.pk}/", {"is_staff": False}).data["is_staff"])

    def test_patch_only_changes_the_fields_sent(self):
        c = self.as_(self.admin)
        c.patch(f"/api/admin/users/{self.bob.pk}/", {"email": "b2@x.fr"})  # ni is_active ni is_staff envoyés
        bob = User.objects.get(pk=self.bob.pk)
        self.assertTrue(bob.is_active)
        self.assertFalse(bob.is_staff)
        c.patch("/api/admin/settings/", {})
        self.assertTrue(SiteSettings.get().allow_registration)

    def test_self_protection(self):
        c = self.as_(self.admin)
        url = f"/api/admin/users/{self.admin.pk}/"
        self.assertEqual(c.patch(url, {"is_active": False}).status_code, 400)
        self.assertEqual(c.patch(url, {"is_staff": False}).status_code, 400)
        self.assertEqual(c.delete(url).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk, is_active=True, is_staff=True).exists())

    def test_the_last_active_admin_cannot_be_removed(self):
        self.root.is_staff = False
        self.root.save()  # il ne reste que `admin` comme administrateur
        self.as_(self.root)  # superutilisateur non-staff : agit via le service
        from accounts import admin_services as svc
        from rest_framework.exceptions import ValidationError
        for call in (lambda: svc.update_user(self.root, self.admin, is_active=False),
                     lambda: svc.update_user(self.root, self.admin, is_staff=False),
                     lambda: svc.delete_user(self.root, self.admin)):
            with self.assertRaises(ValidationError):
                call()

    def test_only_a_superuser_can_touch_a_superuser(self):
        c = self.as_(self.admin)
        url = f"/api/admin/users/{self.root.pk}/"
        self.assertEqual(c.patch(url, {"is_active": False}).status_code, 403)
        self.assertEqual(c.delete(url).status_code, 403)
        self.assertEqual(c.post(f"{url}reset-password/").status_code, 403)
        self.assertEqual(self.as_(self.root).patch(f"/api/admin/users/{self.admin.pk}/", {"email": "a2@x.fr"}).status_code, 200)

    def test_reset_password(self):
        res = self.as_(self.admin).post(f"/api/admin/users/{self.alice.pk}/reset-password/")
        pwd = res.data["generated_password"]
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "alice", "password": PW}).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/token/", {"username": "alice", "password": pwd}).status_code, 200)
        self.as_(self.admin)
        self.assertEqual(self.client.post(f"/api/admin/users/{self.alice.pk}/reset-password/", {"password": "123"}).status_code, 400)
        chosen = "Autre-Mot-De-Passe-77"
        self.assertIsNone(self.client.post(f"/api/admin/users/{self.alice.pk}/reset-password/", {"password": chosen}).data["generated_password"])

    def test_last_login_is_recorded(self):
        self.assertIsNone(User.objects.get(username="alice").last_login)
        self.client.post("/api/auth/token/", {"username": "alice", "password": PW})
        self.assertIsNotNone(User.objects.get(username="alice").last_login)


class AdminDeleteUserTests(AdminBase):
    def test_delete_user_without_projects_keeps_history(self):
        p = create_project(self.alice, "P")
        Membership.objects.create(project=p, user=self.bob, role="member")
        t = Task.objects.create(project=p, title="T", assignee=self.bob)
        Comment.objects.create(task=t, author=self.bob, content="salut")
        res = self.as_(self.admin).delete(f"/api/admin/users/{self.bob.pk}/")
        self.assertEqual(res.status_code, 204)
        t.refresh_from_db()
        self.assertIsNone(t.assignee)
        self.assertEqual(t.comments.count(), 1)
        self.assertIsNone(t.comments.first().author)
        self.assertFalse(Membership.objects.filter(project=p, user_id=self.bob.pk).exists())
        self.client.force_authenticate(self.alice)
        c = self.client.get(f"/api/projects/{p.pk}/tasks/{t.pk}/comments/").data[0]
        self.assertEqual(c["author_name"], "Utilisateur supprimé")

    def test_owner_must_choose_an_heir(self):
        p = create_project(self.alice, "P")
        Membership.objects.create(project=p, user=self.bob, role="member")
        c = self.as_(self.admin)
        info = c.get(f"/api/admin/users/{self.alice.pk}/").data["owned_projects"]
        self.assertEqual(info, [{"id": p.pk, "name": "P", "other_members": 1}])
        res = c.delete(f"/api/admin/users/{self.alice.pk}/")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["owned_projects"][0]["name"], "P")
        self.assertTrue(User.objects.filter(pk=self.alice.pk).exists())  # rien n'a bougé

    def test_transfer_to_heir(self):
        p = create_project(self.alice, "P")
        Membership.objects.create(project=p, user=self.bob, role="member")
        res = self.as_(self.admin).delete(f"/api/admin/users/{self.alice.pk}/?transfer_to={self.bob.pk}")
        self.assertEqual(res.status_code, 204)
        p.refresh_from_db()
        self.assertEqual(p.owner, self.bob)
        self.assertEqual(Membership.objects.get(project=p, user=self.bob).role, "owner")
        self.assertEqual(Membership.objects.filter(project=p).count(), 1)

    def test_heir_must_be_another_active_user(self):
        create_project(self.alice, "P")
        c = self.as_(self.admin)
        url = f"/api/admin/users/{self.alice.pk}/"
        self.assertEqual(c.delete(f"{url}?transfer_to={self.alice.pk}").status_code, 400)
        self.bob.is_active = False
        self.bob.save()
        self.assertEqual(c.delete(f"{url}?transfer_to={self.bob.pk}").status_code, 400)
        self.assertEqual(c.delete(f"{url}?transfer_to=9999").status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.alice.pk).exists())

    def test_delete_solo_projects_but_still_require_heir_for_shared_ones(self):
        solo = create_project(self.alice, "Solo")
        shared = create_project(self.alice, "Partagé")
        Membership.objects.create(project=shared, user=self.bob, role="member")
        c = self.as_(self.admin)
        url = f"/api/admin/users/{self.alice.pk}/"
        self.assertEqual(c.delete(f"{url}?delete_solo=1").status_code, 409)
        self.assertTrue(Project.objects.filter(pk=solo.pk).exists())  # annulé en bloc
        self.assertEqual(c.delete(f"{url}?delete_solo=1&transfer_to={self.bob.pk}").status_code, 204)
        self.assertFalse(Project.objects.filter(pk=solo.pk).exists())
        self.assertEqual(Project.objects.get(pk=shared.pk).owner, self.bob)

    def test_solo_project_only_owner_requires_no_heir_when_deleting_it(self):
        create_project(self.alice, "Solo")
        self.assertEqual(self.as_(self.admin).delete(f"/api/admin/users/{self.alice.pk}/?delete_solo=1").status_code, 204)
        self.assertEqual(Project.objects.count(), 0)


class AdminProjectTests(AdminBase):
    def test_list_sees_every_project_and_counts(self):
        p = create_project(self.alice, "Alpha")
        Membership.objects.create(project=p, user=self.bob, role="member")
        Task.objects.create(project=p, title="a")
        Task.objects.create(project=p, title="b", status="done")
        create_project(self.bob, "Beta")
        rows = self.as_(self.admin).get("/api/admin/projects/").data
        self.assertEqual([r["name"] for r in rows], ["Alpha", "Beta"])
        self.assertEqual((rows[0]["owner"], rows[0]["members"], rows[0]["tasks"], rows[0]["done"]), ("alice", 2, 2, 1))
        self.assertEqual([r["name"] for r in self.client.get("/api/admin/projects/", {"q": "bob"}).data], ["Beta"])

    def test_delete_and_transfer(self):
        p = create_project(self.alice, "Alpha")
        Membership.objects.create(project=p, user=self.bob, role="member")
        c = self.as_(self.admin)
        self.assertEqual(c.post(f"/api/admin/projects/{p.pk}/transfer/", {"user_id": self.bob.pk}).data["owner"], "bob")
        self.assertEqual(Membership.objects.get(project=p, user=self.alice).role, "member")
        self.assertEqual(Membership.objects.filter(project=p, role="owner").count(), 1)
        self.assertEqual(c.post(f"/api/admin/projects/{p.pk}/transfer/", {"user_id": 9999}).status_code, 400)
        self.assertEqual(c.delete(f"/api/admin/projects/{p.pk}/").status_code, 204)
        self.assertFalse(Project.objects.filter(pk=p.pk).exists())

    def test_transfer_to_a_non_member_adds_them_as_owner(self):
        p = create_project(self.alice, "Alpha")
        self.as_(self.admin).post(f"/api/admin/projects/{p.pk}/transfer/", {"user_id": self.bob.pk})
        self.assertEqual(Membership.objects.get(project=p, user=self.bob).role, "owner")


class AdminSettingsAndAuditTests(AdminBase):
    def test_registration_can_be_closed_and_reopened(self):
        self.assertTrue(self.client.get("/api/auth/config/").data["registration_open"])
        self.as_(self.admin).patch("/api/admin/settings/", {"allow_registration": False})
        self.client.force_authenticate(None)
        self.assertFalse(self.client.get("/api/auth/config/").data["registration_open"])
        res = self.client.post("/api/auth/register/", {"username": "zed", "email": "z@x.fr", "password": PW})
        self.assertEqual(res.status_code, 403)
        self.assertFalse(User.objects.filter(username="zed").exists())
        self.as_(self.admin).patch("/api/admin/settings/", {"allow_registration": True})
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/register/", {"username": "zed", "email": "z@x.fr", "password": PW}).status_code, 201)

    def test_admin_can_still_create_users_when_registration_is_closed(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={"allow_registration": False})
        res = self.as_(self.admin).post("/api/admin/users/", {"username": "zed", "email": "z@x.fr"})
        self.assertEqual(res.status_code, 201)

    def test_every_action_is_audited_without_secrets(self):
        c = self.as_(self.admin)
        u = c.post("/api/admin/users/", {"username": "carol", "email": "c@x.fr", "password": PW}).data
        c.patch(f"/api/admin/users/{u['id']}/", {"is_active": False})
        c.patch(f"/api/admin/users/{u['id']}/", {"is_active": True})
        c.patch(f"/api/admin/users/{u['id']}/", {"is_staff": True})
        c.patch(f"/api/admin/users/{u['id']}/", {"is_staff": False})
        c.patch(f"/api/admin/users/{u['id']}/", {"email": "c2@x.fr"})
        c.post(f"/api/admin/users/{u['id']}/reset-password/", {"password": "Autre-Mot-De-Passe-77"})
        c.patch("/api/admin/settings/", {"allow_registration": False})
        c.delete(f"/api/admin/users/{u['id']}/")
        self.assertEqual(self.actions(), ["user.create", "user.deactivate", "user.activate", "user.promote",
                                          "user.demote", "user.update", "user.password_reset", "settings.update", "user.delete"])
        dump = str(list(AuditLog.objects.values()))
        self.assertNotIn(PW, dump)
        self.assertNotIn("Autre-Mot-De-Passe-77", dump)
        self.assertTrue(all(a.actor_name == "admin" for a in AuditLog.objects.all()))

    def test_failed_actions_are_not_audited(self):
        c = self.as_(self.admin)
        c.patch(f"/api/admin/users/{self.admin.pk}/", {"is_active": False})
        c.post("/api/admin/users/", {"username": "alice", "email": "n@x.fr"})
        c.delete(f"/api/admin/users/{self.root.pk}/")
        self.assertEqual(self.actions(), [])

    def test_audit_list_newest_first_with_filter_and_survives_actor_deletion(self):
        c = self.as_(self.admin)
        c.post("/api/admin/users/", {"username": "carol", "email": "c@x.fr"})
        c.patch("/api/admin/settings/", {"allow_registration": False})
        rows = c.get("/api/admin/audit/").data
        self.assertEqual([r["action"] for r in rows], ["settings.update", "user.create"])
        self.assertEqual(rows[0]["details"], {"allow_registration": [True, False]})
        self.assertEqual([r["action"] for r in c.get("/api/admin/audit/", {"action": "user"}).data], ["user.create"])
        self.as_(self.root).delete(f"/api/admin/users/{self.admin.pk}/")
        self.assertEqual(AuditLog.objects.filter(actor_name="admin").count(), 2)  # le nom reste lisible

    def test_settings_unchanged_values_are_not_logged(self):
        self.as_(self.admin).patch("/api/admin/settings/", {"allow_registration": True})
        self.assertEqual(self.actions(), [])

    def test_stats(self):
        p = create_project(self.alice, "P")
        Task.objects.create(project=p, title="a")
        Task.objects.create(project=p, title="b", status="done")
        self.bob.is_active = False
        self.bob.save()
        s = self.as_(self.admin).get("/api/admin/stats/").data
        self.assertEqual(s["users"], {"total": 4, "active": 3, "inactive": 1, "admins": 2, "new_30_days": 4, "active_30_days": 0})
        self.assertEqual((s["projects"], s["tasks"]["total"], s["tasks"]["done"]), (1, 2, 1))
        self.assertEqual(len(s["signups_weekly"]), 8)
        self.assertEqual(sum(w["count"] for w in s["signups_weekly"]), 4)
        self.assertEqual(len(s["recent_users"]), 4)
        self.assertTrue(s["registration_open"])
        self.assertIn(s["planning_engine"]["name"], ("rust", "python"))
        self.assertIn("rust_available", s["planning_engine"])
