from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from projects.models import Membership
from projects.services import create_project

from .models import Task

User = get_user_model()
D = date


class RecurringTaskTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.viewer = User.objects.create_user("vera", password="pw-test-123")
        self.project = create_project(self.alice, "P")
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        Membership.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.client.force_authenticate(self.alice)

    def make(self, recurrence="weekly", a=D(2026, 10, 5), b=D(2026, 10, 7), **kw):
        return Task.objects.create(project=self.project, title="Rapport", recurrence=recurrence, start_date=a, due_date=b, **kw)

    def done(self, task, user=None):
        self.client.force_authenticate(user or self.alice)
        res = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{task.pk}/", {"status": "done"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        return res

    def children(self, task):
        return list(Task.objects.filter(recurrence_of=task))

    def test_completing_a_weekly_task_creates_the_next_one_with_the_same_duration(self):
        t = self.make()
        self.done(t)
        (nxt,) = self.children(t)
        self.assertEqual((nxt.start_date, nxt.due_date, nxt.status), (D(2026, 10, 12), D(2026, 10, 14), "todo"))
        self.assertEqual((nxt.title, nxt.recurrence), ("Rapport", "weekly"))

    def test_the_series_continues_and_never_duplicates(self):
        t = self.make()
        self.done(t)
        self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t.pk}/", {"status": "todo"}, format="json")  # on rouvre
        self.done(t)  # on re-termine : pas de doublon
        self.assertEqual(len(self.children(t)), 1)
        nxt = self.children(t)[0]
        self.done(nxt)
        self.assertEqual(Task.objects.filter(title="Rapport").count(), 3)
        self.assertEqual(Task.objects.get(recurrence_of=nxt).due_date, D(2026, 10, 21))

    def test_each_rule(self):
        cases = [("daily", D(2026, 10, 9), D(2026, 10, 10)), ("weekdays", D(2026, 10, 9), D(2026, 10, 12)),  # vendredi → lundi
                 ("weekly", D(2026, 10, 9), D(2026, 10, 16)), ("monthly", D(2026, 10, 9), D(2026, 11, 9)),
                 ("monthly", D(2026, 1, 31), D(2026, 2, 28)), ("monthly", D(2026, 12, 15), D(2027, 1, 15)),
                 ("monthly", D(2028, 1, 31), D(2028, 2, 29))]
        for rule, due, expected in cases:
            t = Task.objects.create(project=self.project, title=f"{rule}{due}", recurrence=rule, due_date=due)
            self.done(t)
            self.assertEqual(self.children(t)[0].due_date, expected, (rule, due))

    def test_working_day_projects_never_land_on_a_weekend(self):
        self.project.skip_weekends = True
        self.project.save()
        t = Task.objects.create(project=self.project, title="Daily", recurrence="daily", start_date=D(2026, 10, 9), due_date=D(2026, 10, 9))
        self.done(t)
        nxt = self.children(t)[0]
        self.assertEqual((nxt.start_date, nxt.due_date), (D(2026, 10, 12), D(2026, 10, 12)))

    def test_copies_assignee_priority_and_milestone_but_not_dependencies(self):
        pre = Task.objects.create(project=self.project, title="Pré")
        t = self.make(assignee=self.bob, priority=1, is_milestone=True)
        t.dependencies.set([pre])
        self.done(t)
        nxt = self.children(t)[0]
        self.assertEqual((nxt.assignee, nxt.priority, nxt.is_milestone, nxt.dependencies.count()), (self.bob, 1, True, 0))

    def test_tasks_without_dates_or_with_one_date(self):
        t = Task.objects.create(project=self.project, title="Sans date", recurrence="weekly")
        self.done(t)
        self.assertEqual((self.children(t)[0].start_date, self.children(t)[0].due_date), (None, None))
        only_due = Task.objects.create(project=self.project, title="Fin seule", recurrence="weekly", due_date=D(2026, 10, 9))
        self.done(only_due)
        self.assertEqual((self.children(only_due)[0].start_date, self.children(only_due)[0].due_date), (None, D(2026, 10, 16)))
        only_start = Task.objects.create(project=self.project, title="Début seul", recurrence="weekly", start_date=D(2026, 10, 9))
        self.done(only_start)
        self.assertEqual((self.children(only_start)[0].start_date, self.children(only_start)[0].due_date), (D(2026, 10, 16), None))

    def test_a_non_recurring_task_creates_nothing_and_other_status_changes_neither(self):
        plain = self.make(recurrence="")
        self.done(plain)
        self.assertEqual(self.children(plain), [])
        t = self.make()
        self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t.pk}/", {"status": "doing"}, format="json")
        self.assertEqual(self.children(t), [])

    def test_a_task_created_already_done_still_spawns(self):
        res = self.client.post(f"/api/projects/{self.project.pk}/tasks/", {"title": "x", "status": "done", "recurrence": "daily", "due_date": "2026-10-09"}, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Task.objects.filter(recurrence_of=res.data["id"]).count(), 1)

    def test_a_member_can_complete_but_a_viewer_cannot(self):
        t = self.make()
        self.client.force_authenticate(self.viewer)
        self.assertEqual(self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t.pk}/", {"status": "done"}, format="json").status_code, 403)
        self.assertEqual(self.children(t), [])
        self.done(t, self.bob)
        self.assertEqual(len(self.children(t)), 1)

    def test_the_rule_is_validated_and_exposed(self):
        res = self.client.post(f"/api/projects/{self.project.pk}/tasks/", {"title": "x", "recurrence": "hourly"}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post(f"/api/projects/{self.project.pk}/tasks/", {"title": "x", "recurrence": "weekly"}, format="json")
        self.assertEqual((res.status_code, res.data["recurrence"], res.data["recurrence_of"]), (201, "weekly", None))
        child_url = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{res.data['id']}/", {"status": "done"}, format="json")
        child = Task.objects.get(recurrence_of=res.data["id"])
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/tasks/{child.pk}/").data["recurrence_of"], res.data["id"])

    def test_deleting_the_origin_keeps_the_next_occurrence(self):
        t = self.make()
        self.done(t)
        nxt = self.children(t)[0]
        t.delete()
        nxt.refresh_from_db()
        self.assertIsNone(nxt.recurrence_of)
