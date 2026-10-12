from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Membership, ProjectInvite
from .services import create_project

User = get_user_model()


class InviteLinkTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user("alice", "a@x.fr", "pw-test-123")
        self.bob = User.objects.create_user("bob", "b@x.fr", "pw-test-123")
        self.carol = User.objects.create_user("carol", "c@x.fr", "pw-test-123")
        self.project = create_project(self.alice, "Projet A")
        self.url = f"/api/projects/{self.project.pk}/invites/"

    def link(self, **body):
        self.client.force_authenticate(self.alice)
        res = self.client.post(self.url, body, format="json")
        self.client.force_authenticate(None)
        return res

    def test_owner_creates_a_link_and_the_token_is_not_stored(self):
        res = self.link(role="viewer", days=7, max_uses=3)
        self.assertEqual(res.status_code, 201)
        token = res.data["token"]
        self.assertGreater(len(token), 30)
        invite = ProjectInvite.objects.get()
        self.assertNotIn(token, invite.token_hash)  # seule l'empreinte est conservée
        self.assertEqual((invite.role, invite.max_uses, invite.uses), ("viewer", 3, 0))
        self.client.force_authenticate(self.alice)
        listed = self.client.get(self.url).data  # la liste ne renvoie jamais le jeton
        self.assertEqual(len(listed), 1)
        self.assertNotIn("token", listed[0])

    def test_only_the_owner_manages_links(self):
        self.client.force_authenticate(self.alice)
        self.client.post(f"/api/projects/{self.project.pk}/members/", {"identifier": "bob"})
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_authenticate(self.carol)  # non membre : le projet n'existe pas pour elle
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 404)

    def test_link_validation(self):
        self.assertEqual(self.link(role="owner").status_code, 400)
        self.assertEqual(self.link(days=365).status_code, 400)
        self.assertEqual(self.link(max_uses=0).status_code, 400)
        self.assertEqual(self.link(max_uses=101).status_code, 400)

    def test_preview_is_public_and_reveals_only_the_project_name(self):
        token = self.link().data["token"]
        res = self.client.get(f"/api/invites/{token}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data, {"project_name": "Projet A", "role": "member", "inviter": "alice"})

    def test_accepting_adds_the_member_with_the_link_role(self):
        token = self.link(role="viewer").data["token"]
        self.client.force_authenticate(self.bob)
        res = self.client.post(f"/api/invites/{token}/accept/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data["project_id"], res.data["already_member"]), (self.project.pk, False))
        self.assertEqual(Membership.objects.get(project=self.project, user=self.bob).role, "viewer")
        self.assertEqual(ProjectInvite.objects.get().uses, 1)

    def test_accepting_requires_an_account(self):
        token = self.link().data["token"]
        self.assertEqual(self.client.post(f"/api/invites/{token}/accept/").status_code, 401)

    def test_existing_member_is_neither_counted_nor_demoted(self):
        token = self.link(role="viewer").data["token"]
        self.client.force_authenticate(self.alice)
        res = self.client.post(f"/api/invites/{token}/accept/")
        self.assertTrue(res.data["already_member"])
        self.assertEqual(Membership.objects.get(project=self.project, user=self.alice).role, "owner")
        self.assertEqual(ProjectInvite.objects.get().uses, 0)

    def test_usage_limit(self):
        token = self.link(max_uses=1).data["token"]
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.post(f"/api/invites/{token}/accept/").status_code, 200)
        self.client.force_authenticate(self.carol)
        self.assertEqual(self.client.post(f"/api/invites/{token}/accept/").status_code, 404)
        self.assertFalse(Membership.objects.filter(project=self.project, user=self.carol).exists())

    def test_expired_revoked_and_unknown_links_all_answer_404(self):
        token = self.link().data["token"]
        ProjectInvite.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(f"/api/invites/{token}/").status_code, 404)
        token = self.link().data["token"]
        self.client.force_authenticate(self.alice)
        invite = ProjectInvite.objects.filter(expires_at__gt=timezone.now()).get()
        self.assertEqual(self.client.delete(f"{self.url}{invite.pk}/").status_code, 204)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/invites/{token}/").status_code, 404)
        self.assertEqual(self.client.get("/api/invites/n-importe-quoi/").status_code, 404)
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.post(f"/api/invites/{token}/accept/").status_code, 404)

    def test_revoking_someone_elses_link_is_impossible(self):
        other = create_project(self.bob, "Projet B")
        self.client.force_authenticate(self.bob)
        res = self.client.post(f"/api/projects/{other.pk}/invites/", {}, format="json")
        invite_id = res.data["id"]
        self.client.force_authenticate(self.alice)  # propriétaire d'un autre projet
        self.assertEqual(self.client.delete(f"{self.url}{invite_id}/").status_code, 404)
        self.assertEqual(ProjectInvite.objects.get(pk=invite_id).revoked, False)

    def test_active_links_are_capped(self):
        for _ in range(20):
            self.assertEqual(self.link().status_code, 201)
        self.assertEqual(self.link().status_code, 400)

    def test_the_preview_is_rate_limited(self):
        codes = {self.client.get("/api/invites/x/").status_code for _ in range(35)}
        self.assertIn(429, codes)


class MemberCandidatesTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user("alice", "a@x.fr", "pw-test-123")
        for name in ("lea", "leon", "bob"):
            User.objects.create_user(name, f"{name}@x.fr", "pw-test-123")
        User.objects.create_user("lena-inactive", "n@x.fr", "pw-test-123", is_active=False)
        self.project = create_project(self.alice, "Projet A")
        self.url = f"/api/projects/{self.project.pk}/member-candidates/"
        self.client.force_authenticate(self.alice)

    def names(self, q):
        res = self.client.get(self.url, {"q": q})
        self.assertEqual(res.status_code, 200)
        return [u["username"] for u in res.data]

    def test_prefix_search_ignores_a_leading_at_and_case(self):
        self.assertEqual(self.names("le"), ["lea", "leon"])
        self.assertEqual(self.names("@LEO"), ["leon"])

    def test_one_letter_after_the_at_is_enough(self):
        self.assertEqual(self.names("@l"), ["lea", "leon"])
        self.assertEqual(self.names("b"), ["bob"])

    def test_empty_queries_return_nothing_and_inactive_or_self_are_excluded(self):
        self.assertEqual(self.names("@"), [])
        self.assertEqual(self.names("  "), [])
        self.assertEqual(self.names("len"), [])  # compte désactivé
        self.assertEqual(self.names("al"), [])  # moi (déjà membre)

    def test_current_members_are_excluded(self):
        self.client.post(f"/api/projects/{self.project.pk}/members/", {"identifier": "lea"})
        self.assertEqual(self.names("le"), ["leon"])

    def test_only_the_owner_can_search_and_outsiders_get_404(self):
        self.client.post(f"/api/projects/{self.project.pk}/members/", {"identifier": "bob"})
        self.client.force_authenticate(User.objects.get(username="bob"))
        self.assertEqual(self.client.get(self.url, {"q": "le"}).status_code, 403)
        self.client.force_authenticate(User.objects.get(username="leon"))
        self.assertEqual(self.client.get(self.url, {"q": "le"}).status_code, 404)

    def test_results_are_capped_and_rate_limited(self):
        for i in range(12):
            User.objects.create_user(f"zed{i:02d}", f"z{i}@x.fr", "pw-test-123")
        self.assertEqual(len(self.names("zed")), 8)
        codes = {self.client.get(self.url, {"q": "zed"}).status_code for _ in range(65)}
        self.assertIn(429, codes)
