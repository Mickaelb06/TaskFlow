from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from projects.models import Membership
from projects.services import create_project

from . import planning
from .models import Task

User = get_user_model()
TODAY = date(2026, 10, 15)
D = lambda n: TODAY + timedelta(days=n)
at = lambda d: timezone.make_aware(datetime.combine(d, time(12, 0)))


class Base(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.project = create_project(self.alice, "Alpha")
        Membership.objects.create(project=self.project, user=self.bob, role="member")

    def task(self, title, who=None, start=None, end=None, created=-30, done_on=None, project=None, **kw):
        t = Task.objects.create(project=project or self.project, title=title, assignee=who,
                                start_date=D(start) if start is not None else None,
                                due_date=D(end) if end is not None else None,
                                status="done" if done_on is not None else kw.pop("status", "todo"), **kw)
        Task.objects.filter(pk=t.pk).update(created_at=at(D(created)), completed_at=at(D(done_on)) if done_on is not None else None)
        t.refresh_from_db()
        return t


class CompletionTimestampTests(Base):
    def test_status_changes_set_and_clear_completed_at(self):
        self.client.force_authenticate(self.alice)
        t = self.client.post(f"/api/projects/{self.project.pk}/tasks/", {"title": "x"}).data
        self.assertIsNone(t["completed_at"])
        done = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t['id']}/", {"status": "done"}).data
        self.assertIsNotNone(done["completed_at"])
        again = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t['id']}/", {"status": "done"}).data
        self.assertEqual(again["completed_at"], done["completed_at"])  # pas réécrite
        reopened = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{t['id']}/", {"status": "doing"}).data
        self.assertIsNone(reopened["completed_at"])

    def test_completed_at_cannot_be_forged(self):
        self.client.force_authenticate(self.alice)
        t = self.client.post(f"/api/projects/{self.project.pk}/tasks/",
                             {"title": "x", "completed_at": "2020-01-01T00:00:00Z"}).data
        self.assertIsNone(t["completed_at"])


class ProjectStatsTests(Base):
    def test_status_priority_and_burnup(self):
        self.task("a", created=-10, done_on=-5)
        self.task("b", created=-3, priority=1)
        self.task("c", created=0, status="doing")
        s = planning.stats(list(self.project.tasks.all()), TODAY)
        self.assertEqual(s["status_counts"], {"todo": 1, "doing": 1, "done": 1})
        self.assertEqual(s["priority_counts"], {"1": 1, "2": 1, "3": 0})
        self.assertEqual(len(s["burnup"]), 30)
        by_date = {p["date"]: p for p in s["burnup"]}
        self.assertEqual((by_date[D(-11)]["created"], by_date[D(-11)]["done"]), (0, 0))
        self.assertEqual((by_date[D(-6)]["created"], by_date[D(-6)]["done"]), (1, 0))
        self.assertEqual((by_date[D(-5)]["created"], by_date[D(-5)]["done"]), (1, 1))
        self.assertEqual((by_date[D(0)]["created"], by_date[D(0)]["done"]), (3, 1))

    def test_velocity_compares_two_weeks(self):
        for n in (-1, -3, -6):
            self.task(f"w{n}", done_on=n)
        for n in (-8, -12):
            self.task(f"p{n}", done_on=n)
        self.task("hors fenêtre", done_on=-20)
        v = planning.stats(list(self.project.tasks.all()), TODAY)["velocity"]
        self.assertEqual(v, {"this_week": 3, "last_week": 2})

    def test_recent_done_and_due_soon(self):
        self.task("vieille", self.bob, done_on=-9)
        self.task("récente", self.bob, done_on=-1)
        self.task("bientôt", self.alice, 0, 3)
        self.task("lointaine", self.alice, 0, 30)
        self.task("passée", self.alice, -5, -2)
        s = planning.stats(list(self.project.tasks.select_related("assignee")), TODAY)
        self.assertEqual([r["title"] for r in s["recent_done"]], ["récente", "vieille"])
        self.assertEqual([r["title"] for r in s["due_soon"]], ["bientôt"])

    def test_health(self):
        base = {"total": 4, "done": 1, "slip_days": None, "late_count": 0, "risks": []}
        self.assertEqual(planning.health({**base, "total": 0, "done": 0}), "empty")
        self.assertEqual(planning.health({**base, "done": 4}), "done")
        self.assertEqual(planning.health({**base, "slip_days": 2}), "late")
        self.assertEqual(planning.health({**base, "late_count": 1}), "risk")
        self.assertEqual(planning.health({**base, "risks": [{"severity": "low"}]}), "ok")


class UserDashboardTests(Base):
    def test_my_focus_buckets_and_kpis(self):
        self.task("en retard", self.alice, -6, -2)
        self.task("aujourd'hui", self.alice, -1, 1)
        self.task("en cours sans date", self.alice, status="doing")
        self.task("jeudi", self.alice, 2, 3)
        self.task("sans date", self.alice)
        self.task("à bob", self.bob, -6, -2)
        self.task("fait", self.alice, done_on=-1)
        d = planning.user_dashboard(self.alice, TODAY)
        self.assertEqual(d["kpis"]["late"], 1)
        self.assertEqual(d["kpis"]["today"], 2)
        self.assertEqual(d["kpis"]["upcoming"], 1)
        self.assertEqual(d["kpis"]["unscheduled"], 2)
        self.assertEqual(d["kpis"]["done_this_week"], 1)
        self.assertEqual([t["title"] for t in d["focus"]][0], "en retard")
        self.assertNotIn("à bob", [t["title"] for t in d["focus"]])
        self.assertEqual(len(d["week"]), 7)
        self.assertEqual([t["title"] for t in d["week"][3]["tasks"]], ["jeudi"])
        self.assertEqual(sum(x["count"] for x in d["done_series"]), 1)

    def test_projects_cards_and_team_alerts(self):
        self.task("retard de bob", self.bob, -6, -3)
        d = planning.user_dashboard(self.alice, TODAY)
        card = d["projects"][0]
        self.assertEqual((card["name"], card["role"], card["team_late"]), ("Alpha", "owner", 1))
        self.assertIn(card["health"], ("risk", "late"))
        self.assertEqual(d["alerts"][0]["user"], "bob")
        self.assertEqual(d["alerts"][0]["days_late"], 3)  # fin au jour -3
        # bob ne reçoit pas d'alerte sur lui-même
        self.assertEqual(planning.user_dashboard(self.bob, TODAY)["alerts"], [])

    def test_only_my_projects_are_included(self):
        other = create_project(self.bob, "Secret de Bob")
        self.task("privée", self.bob, 0, 1, project=other)
        d = planning.user_dashboard(self.alice, TODAY)
        self.assertEqual([c["name"] for c in d["projects"]], ["Alpha"])
        self.assertNotIn("privée", str(d))

    def test_endpoint_requires_login_and_returns_data(self):
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)
        self.client.force_authenticate(self.alice)
        res = self.client.get("/api/dashboard/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual({"kpis", "focus", "week", "projects", "alerts", "done_series"}, set(res.data))

    def test_insights_endpoint_exposes_stats(self):
        self.client.force_authenticate(self.alice)
        res = self.client.get(f"/api/projects/{self.project.pk}/insights/")
        self.assertIn("burnup", res.data["stats"])
