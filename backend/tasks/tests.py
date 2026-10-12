from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from projects.models import Membership
from projects.services import create_project

from .models import Task

User = get_user_model()


class TaskApiTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.carol = User.objects.create_user("carol", password="pw-test-123")
        self.project = create_project(self.alice, "Projet A")
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        Membership.objects.create(project=self.project, user=self.carol, role="viewer")
        self.url = f"/api/projects/{self.project.pk}/tasks/"

    def test_owner_can_create_task_with_default_priority(self):
        self.client.force_authenticate(self.alice)
        res = self.client.post(self.url, {"title": "Écrire le CDC"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["priority"], 2)

    def test_non_member_gets_404(self):
        dave = User.objects.create_user("dave", password="pw-test-123")
        self.client.force_authenticate(dave)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_invalid_priority_rejected(self):
        self.client.force_authenticate(self.alice)
        self.assertEqual(self.client.post(self.url, {"title": "x", "priority": 9}).status_code, 400)

    def test_unauthenticated_rejected(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_viewer_can_read_but_not_write(self):
        task = Task.objects.create(project=self.project, title="T")
        self.client.force_authenticate(self.carol)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.post(self.url, {"title": "x"}).status_code, 403)
        self.assertEqual(self.client.patch(f"{self.url}{task.pk}/", {"status": "done"}).status_code, 403)
        self.assertEqual(self.client.delete(f"{self.url}{task.pk}/").status_code, 403)

    def test_assignee_must_be_project_member(self):
        dave = User.objects.create_user("dave", password="pw-test-123")
        self.client.force_authenticate(self.alice)
        res = self.client.post(self.url, {"title": "x", "assignee": dave.pk})
        self.assertEqual(res.status_code, 400)
        res = self.client.post(self.url, {"title": "x", "assignee": self.bob.pk})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["assignee_name"], "bob")

    def test_member_updates_status(self):
        task = Task.objects.create(project=self.project, title="T")
        self.client.force_authenticate(self.bob)
        res = self.client.patch(f"{self.url}{task.pk}/", {"status": "doing"})
        self.assertEqual(res.data["status"], "doing")

    def test_calendar_range_and_status_filters(self):
        Task.objects.create(project=self.project, title="oct", due_date="2026-10-10")
        Task.objects.create(project=self.project, title="nov", due_date="2026-11-05", status="done")
        Task.objects.create(project=self.project, title="sans date")
        self.client.force_authenticate(self.alice)
        res = self.client.get(self.url, {"due_after": "2026-10-01", "due_before": "2026-10-31"})
        self.assertEqual([t["title"] for t in res.data], ["oct"])
        res = self.client.get(self.url, {"status": "done"})
        self.assertEqual([t["title"] for t in res.data], ["nov"])

    def test_removed_member_tasks_become_unassigned(self):
        task = Task.objects.create(project=self.project, title="T", assignee=self.bob)
        self.client.force_authenticate(self.alice)
        self.client.delete(f"/api/projects/{self.project.pk}/members/{self.bob.pk}/")
        task.refresh_from_db()
        self.assertIsNone(task.assignee)


class CommentApiTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.carol = User.objects.create_user("carol", password="pw-test-123")
        self.project = create_project(self.alice, "Projet A")
        Membership.objects.create(project=self.project, user=self.carol, role="viewer")
        self.task = Task.objects.create(project=self.project, title="T")
        self.url = f"/api/projects/{self.project.pk}/tasks/{self.task.pk}/comments/"

    def test_member_comments_and_everyone_reads(self):
        self.client.force_authenticate(self.alice)
        res = self.client.post(self.url, {"content": "Bonjour"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["author_name"], "alice")
        self.client.force_authenticate(self.carol)
        self.assertEqual(len(self.client.get(self.url).data), 1)

    def test_viewer_cannot_comment(self):
        self.client.force_authenticate(self.carol)
        self.assertEqual(self.client.post(self.url, {"content": "x"}).status_code, 403)

    def test_task_from_other_project_is_404(self):
        other = create_project(self.alice, "Autre")
        self.client.force_authenticate(self.alice)
        res = self.client.get(f"/api/projects/{other.pk}/tasks/{self.task.pk}/comments/")
        self.assertEqual(res.status_code, 404)
