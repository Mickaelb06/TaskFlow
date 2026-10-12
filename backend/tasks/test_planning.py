from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from projects.models import Membership
from projects.services import create_project

from . import planning
from .models import Task

User = get_user_model()
D = lambda n: date(2026, 10, 1) + timedelta(days=n)  # jour 0 = 1er octobre 2026


class PlanningEngineTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.project = create_project(self.alice, "P")

    def task(self, title, start, end, deps=(), **kw):
        t = Task.objects.create(project=self.project, title=title, start_date=D(start), due_date=D(end), **kw)
        t.dependencies.set(deps)
        return t

    def test_cascade_pushes_dependents_but_never_pulls_them_earlier(self):
        a = self.task("A", 0, 2)
        b = self.task("B", 3, 4, [a])
        c = self.task("C", 5, 6, [b])
        a.due_date = D(5)  # A rallongée de 3 jours
        a.save()
        moved = planning.cascade(a)
        b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual((b.start_date, b.due_date), (D(6), D(7)))
        self.assertEqual((c.start_date, c.due_date), (D(8), D(9)))
        self.assertEqual(set(moved), {b.pk, c.pk})
        a.due_date = D(1); a.save()  # A raccourcie : B ne revient pas en arrière
        self.assertEqual(planning.cascade(a), [])

    def test_cascade_leaves_finished_tasks_alone(self):
        a = self.task("A", 0, 5)
        b = self.task("B", 1, 2, [a], status="done")
        planning.cascade(a)
        b.refresh_from_db()
        self.assertEqual(b.start_date, D(1))

    def test_critical_path_is_the_longest_chain(self):
        a = self.task("A", 0, 2)           # 3 j
        b = self.task("B", 3, 4, [a])      # 2 j
        c = self.task("C", 0, 0)           # 1 j, en parallèle
        d = self.task("D", 5, 5, [b, c])   # 1 j
        ids, total = planning.critical_path(list(self.project.tasks.prefetch_related("dependencies")))
        self.assertEqual(ids, [a.pk, b.pk, d.pk])
        self.assertEqual(total, 6)
        self.assertNotIn(c.pk, ids)

    def test_dependency_cycle_detected(self):
        a = self.task("A", 0, 1)
        b = self.task("B", 2, 3, [a])
        self.assertTrue(planning.would_cycle(a, [b]))
        self.assertFalse(planning.would_cycle(b, [a]))

    def test_forecast_propagates_lateness(self):
        a = self.task("A", 0, 2)           # en retard
        self.task("B", 3, 5, [a])
        today = D(10)
        tasks = list(self.project.tasks.prefetch_related("dependencies"))
        # A finit au mieux le jour 10, donc B (3 j) ne finit pas avant le jour 5 + 8 = 13
        self.assertEqual(planning.forecast_end(tasks, today), D(13))

    def test_insights_flags_late_blocked_unassigned_and_deadline(self):
        self.project.deadline = D(6)
        self.project.save()
        a = self.task("A", 0, 2)
        self.task("B", 3, 5, [a])
        data = planning.insights(self.project, today=D(10))
        kinds = {r["type"] for r in data["risks"]}
        self.assertTrue({"late", "deadline"} <= kinds)
        self.assertEqual(data["forecast_end"], D(13))
        self.assertEqual(data["slip_days"], 7)
        self.assertEqual(data["late_count"], 2)
        self.assertEqual(data["progress"], 0)

    def test_progress_is_weighted_by_duration(self):
        self.task("long", 0, 8, status="done")   # 9 j
        self.task("court", 9, 9)                  # 1 j
        self.assertEqual(planning.insights(self.project, today=D(0))["progress"], 90)

    def test_replan_restarts_late_tasks_today_and_cascades(self):
        a = self.task("A", 0, 2)
        b = self.task("B", 3, 4, [a])
        moved = planning.replan(self.project, today=D(10))
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.start_date, a.due_date), (D(10), D(12)))
        self.assertEqual(b.start_date, D(13))
        self.assertEqual(set(moved), {a.pk, b.pk})


class TeamStatusTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.carol = User.objects.create_user("carol", password="pw-test-123")
        self.dave = User.objects.create_user("dave", password="pw-test-123")
        self.project = create_project(self.alice, "P")
        for u in (self.bob, self.carol, self.dave):
            Membership.objects.create(project=self.project, user=u, role="member")

    def task(self, title, who, start, end, **kw):
        return Task.objects.create(project=self.project, title=title, assignee=who,
                                   start_date=D(start), due_date=D(end), **kw)

    def team(self, today=10):
        data = planning.insights(self.project, today=D(today))["team"]
        return {r["username"]: r for r in data}

    def test_states_late_overloaded_ok_free(self):
        self.task("retard", self.bob, 0, 3)                       # fini il y a 7 jours
        for i in range(4):                                         # 4 tâches en parallèle
            self.task(f"p{i}", self.carol, 9, 12)
        self.task("normal", self.alice, 9, 12)
        team = self.team()
        self.assertEqual(team["bob"]["state"], "late")
        self.assertEqual(team["bob"]["late"][0]["days_late"], 7)
        self.assertEqual(team["carol"]["state"], "overloaded")
        self.assertEqual(team["alice"]["state"], "ok")
        self.assertEqual(team["dave"]["state"], "free")

    def test_current_upcoming_and_progress(self):
        self.task("fait", self.bob, 0, 2, status="done")
        self.task("en cours", self.bob, 8, 12)
        self.task("plus tard", self.bob, 15, 17)
        self.task("sans date", self.bob, 0, 0).delete()
        Task.objects.create(project=self.project, title="à planifier", assignee=self.bob)
        bob = self.team()["bob"]
        self.assertEqual([t["title"] for t in bob["current"]], ["en cours"])
        self.assertEqual([t["title"] for t in bob["upcoming"]], ["plus tard"])
        self.assertEqual((bob["done"], bob["total"], bob["unscheduled"]), (1, 4, 1))
        self.assertEqual(bob["state"], "ok")

    def test_a_done_task_is_never_late(self):
        self.task("vieux", self.bob, 0, 2, status="done")
        self.assertEqual(self.team()["bob"]["state"], "free")

    def test_most_urgent_members_come_first_and_unassigned_counted(self):
        self.task("retard", self.dave, 0, 3)
        Task.objects.create(project=self.project, title="orpheline", start_date=D(0), due_date=D(2))
        data = planning.insights(self.project, today=D(10))
        self.assertEqual(data["team"][0]["username"], "dave")
        self.assertEqual(data["unassigned"], {"open": 1, "late": 1})

    def test_team_visible_to_viewers(self):
        Membership.objects.create(project=self.project, user=User.objects.create_user("vera", password="x-pw-123456"), role="viewer")
        self.client.force_authenticate(User.objects.get(username="vera"))
        res = self.client.get(f"/api/projects/{self.project.pk}/insights/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["team"]), 5)


class PlanningApiTests(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.viewer = User.objects.create_user("viewer", password="pw-test-123")
        self.stranger = User.objects.create_user("stranger", password="pw-test-123")
        self.project = create_project(self.alice, "P")
        Membership.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.base = f"/api/projects/{self.project.pk}"

    def test_moving_a_task_pushes_its_dependents(self):
        self.client.force_authenticate(self.alice)
        a = self.client.post(f"{self.base}/tasks/", {"title": "A", "start_date": "2026-10-01", "due_date": "2026-10-03"}).data
        b = self.client.post(f"{self.base}/tasks/", {"title": "B", "start_date": "2026-10-04", "due_date": "2026-10-05",
                                                     "dependencies": [a["id"]]}).data
        self.client.patch(f"{self.base}/tasks/{a['id']}/", {"due_date": "2026-10-10"})
        res = self.client.get(f"{self.base}/tasks/{b['id']}/")
        self.assertEqual((res.data["start_date"], res.data["due_date"]), ("2026-10-11", "2026-10-12"))

    def test_adding_a_dependency_pushes_the_task_after_its_predecessor(self):
        self.client.force_authenticate(self.alice)
        a = self.client.post(f"{self.base}/tasks/", {"title": "A", "start_date": "2026-10-01", "due_date": "2026-10-09"}).data
        b = self.client.post(f"{self.base}/tasks/", {"title": "B", "start_date": "2026-10-02", "due_date": "2026-10-03"}).data
        res = self.client.patch(f"{self.base}/tasks/{b['id']}/", {"dependencies": [a["id"]]})
        self.assertEqual(res.data["start_date"], "2026-10-10")

    def test_cycle_self_dependency_and_foreign_project_rejected(self):
        self.client.force_authenticate(self.alice)
        a = self.client.post(f"{self.base}/tasks/", {"title": "A"}).data
        b = self.client.post(f"{self.base}/tasks/", {"title": "B", "dependencies": [a["id"]]}).data
        self.assertEqual(self.client.patch(f"{self.base}/tasks/{a['id']}/", {"dependencies": [b["id"]]}).status_code, 400)
        self.assertEqual(self.client.patch(f"{self.base}/tasks/{a['id']}/", {"dependencies": [a["id"]]}).status_code, 400)
        other = create_project(self.alice, "Autre")
        foreign = Task.objects.create(project=other, title="X")
        self.assertEqual(self.client.patch(f"{self.base}/tasks/{a['id']}/", {"dependencies": [foreign.pk]}).status_code, 400)

    def test_start_after_due_rejected(self):
        self.client.force_authenticate(self.alice)
        res = self.client.post(f"{self.base}/tasks/", {"title": "A", "start_date": "2026-10-05", "due_date": "2026-10-01"})
        self.assertEqual(res.status_code, 400)

    def test_insights_access_rules(self):
        self.client.force_authenticate(self.viewer)
        res = self.client.get(f"{self.base}/insights/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("critical_path", res.data)
        self.assertEqual(self.client.post(f"{self.base}/replan/").status_code, 403)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get(f"{self.base}/insights/").status_code, 404)

    def test_project_deadline_editable_by_owner(self):
        self.client.force_authenticate(self.alice)
        res = self.client.patch(f"/api/projects/{self.project.pk}/", {"deadline": "2026-12-31"})
        self.assertEqual(res.data["deadline"], "2026-12-31")
