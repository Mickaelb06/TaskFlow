from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from .models import Membership
from .services import create_project

User = get_user_model()


class ProjectMemberTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "a@x.fr", "pw-test-123")
        self.bob = User.objects.create_user("bob", "b@x.fr", "pw-test-123")
        self.carol = User.objects.create_user("carol", "c@x.fr", "pw-test-123")
        self.project = create_project(self.alice, "Projet A")
        self.members_url = f"/api/projects/{self.project.pk}/members/"

    def test_creating_project_makes_creator_owner(self):
        self.client.force_authenticate(self.bob)
        res = self.client.post("/api/projects/", {"name": "Perso"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["role"], "owner")

    def test_projects_list_only_shows_own_projects(self):
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get("/api/projects/").data, [])

    def test_owner_adds_member_by_username_or_email(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.post(self.members_url, {"identifier": "bob"}).status_code, 201)
        res = self.client.post(self.members_url, {"identifier": "C@x.fr", "role": "viewer"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["role"], "viewer")

    def test_add_unknown_or_duplicate_member_rejected(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.post(self.members_url, {"identifier": "nobody"}).status_code, 400)
        self.client.post(self.members_url, {"identifier": "bob"})
        self.assertEqual(self.client.post(self.members_url, {"identifier": "bob"}).status_code, 400)

    def test_cannot_add_second_owner(self):
        self.client.force_authenticate(self.alice)
        res = self.client.post(self.members_url, {"identifier": "bob", "role": "owner"})
        self.assertEqual(res.status_code, 400)

    def test_non_owner_cannot_manage_members(self):
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.get(self.members_url).status_code, 200)
        self.assertEqual(self.client.post(self.members_url, {"identifier": "carol"}).status_code, 403)

    def test_owner_changes_role_and_removes_member(self):
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        self.client.force_authenticate(self.alice)
        res = self.client.patch(f"{self.members_url}{self.bob.pk}/", {"role": "viewer"})
        self.assertEqual(res.data["role"], "viewer")
        self.assertEqual(self.client.delete(f"{self.members_url}{self.bob.pk}/").status_code, 204)

    def test_member_can_leave_but_owner_cannot(self):
        Membership.objects.create(project=self.project, user=self.bob, role="viewer")
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.delete(f"{self.members_url}{self.bob.pk}/").status_code, 204)
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.delete(f"{self.members_url}{self.alice.pk}/").status_code, 400)

    def test_only_owner_can_edit_or_delete_project(self):
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        self.client.force_authenticate(self.bob)
        self.assertEqual(self.client.patch(f"/api/projects/{self.project.pk}/", {"name": "X"}).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/projects/{self.project.pk}/").status_code, 403)
