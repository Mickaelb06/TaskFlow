from datetime import date, datetime, timedelta, timezone as utc
from unittest import mock

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts import admin_services
from accounts.models import Profile
from projects.models import Membership
from projects.services import create_project

from .models import Task, TimeEntry

User = get_user_model()


class TimeCase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.viewer = User.objects.create_user("vera", password="pw-test-123")
        self.dave = User.objects.create_user("dave", password="pw-test-123")
        self.project = create_project(self.alice, "P")
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        Membership.objects.create(project=self.project, user=self.viewer, role="viewer")
        self.t1 = Task.objects.create(project=self.project, title="T1")
        self.t2 = Task.objects.create(project=self.project, title="T2")

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def url(self, task, tail=""):
        return f"/api/projects/{self.project.pk}/tasks/{task.pk}/time/{tail}"

    def at(self, moment):
        return mock.patch("django.utils.timezone.now", return_value=moment)


class TimerTests(TimeCase):
    def test_start_then_stop_records_the_elapsed_minutes(self):
        t0 = datetime(2026, 10, 12, 8, 0, tzinfo=utc.utc)
        with self.at(t0):
            res = self.as_(self.alice).post(self.url(self.t1, "start/"))
        self.assertEqual((res.status_code, res.data["running"], res.data["minutes"]), (201, True, None))
        with self.at(t0 + timedelta(minutes=42, seconds=20)):
            done = self.as_(self.alice).post("/api/timer/")
        self.assertEqual((done.status_code, done.data["minutes"], done.data["running"]), (200, 42, False))
        self.assertEqual(self.as_(self.alice).get(self.url(self.t1)).data["total"], 42)

    def test_a_started_timer_is_visible_across_projects_with_its_context(self):
        self.as_(self.alice).post(self.url(self.t1, "start/"))
        cur = self.client.get("/api/timer/").data
        self.assertEqual((cur["task_title"], cur["project_name"], cur["running"]), ("T1", "P", True))
        self.assertIsNone(self.as_(self.bob).get("/api/timer/").data)  # le chrono des autres ne se voit pas

    def test_only_one_timer_at_a_time_starting_another_stops_the_first(self):
        t0 = datetime(2026, 10, 12, 8, 0, tzinfo=utc.utc)
        with self.at(t0):
            self.as_(self.alice).post(self.url(self.t1, "start/"))
        with self.at(t0 + timedelta(minutes=30)):
            self.as_(self.alice).post(self.url(self.t2, "start/"))
        self.assertEqual(TimeEntry.objects.filter(user=self.alice, minutes__isnull=True).count(), 1)
        self.assertEqual(TimeEntry.objects.get(task=self.t1).minutes, 30)
        self.assertEqual(self.as_(self.alice).get("/api/timer/").data["task"], self.t2.pk)

    def test_stopping_without_a_timer_is_a_clean_error(self):
        self.assertEqual(self.as_(self.alice).post("/api/timer/").status_code, 400)

    def test_a_forgotten_timer_is_capped_at_twelve_hours_and_a_blip_counts_one_minute(self):
        t0 = datetime(2026, 10, 12, 8, 0, tzinfo=utc.utc)
        with self.at(t0):
            self.as_(self.alice).post(self.url(self.t1, "start/"))
        with self.at(t0 + timedelta(days=3)):
            self.assertEqual(self.as_(self.alice).post("/api/timer/").data["minutes"], 720)
        with self.at(t0):
            self.as_(self.alice).post(self.url(self.t1, "start/"))
        with self.at(t0 + timedelta(seconds=4)):
            self.assertEqual(self.as_(self.alice).post("/api/timer/").data["minutes"], 1)

    def test_the_day_is_the_users_local_day(self):
        Profile.objects.update_or_create(user=self.alice, defaults={"timezone": "Asia/Tokyo"})
        with self.at(datetime(2026, 10, 12, 20, 0, tzinfo=utc.utc)):  # 20 h UTC = 05 h le 13 à Tokyo
            res = self.as_(self.alice).post(self.url(self.t1, "start/"))
        self.assertEqual(res.data["day"], date(2026, 10, 13))

    def test_viewer_and_stranger_cannot_track_time(self):
        self.assertEqual(self.as_(self.viewer).post(self.url(self.t1, "start/")).status_code, 403)
        self.assertEqual(self.as_(self.viewer).post(self.url(self.t1), {"minutes": 10}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.dave).post(self.url(self.t1, "start/")).status_code, 404)
        self.assertEqual(self.as_(self.dave).get(self.url(self.t1)).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/timer/").status_code, 401)

    def test_a_task_of_another_project_cannot_be_reached_through_this_one(self):
        other = create_project(self.alice, "Autre")
        foreign = Task.objects.create(project=other, title="Ailleurs")
        self.assertEqual(self.as_(self.alice).post(f"/api/projects/{self.project.pk}/tasks/{foreign.pk}/time/start/").status_code, 404)


class ManualEntryTests(TimeCase):
    def test_add_list_and_total(self):
        r = self.as_(self.alice).post(self.url(self.t1), {"minutes": 90, "day": "2026-10-10", "note": "Maquette"}, format="json")
        self.assertEqual((r.status_code, r.data["minutes"], r.data["day"]), (201, 90, date(2026, 10, 10)))
        self.as_(self.bob).post(self.url(self.t1), {"minutes": 30}, format="json")
        data = self.as_(self.viewer).get(self.url(self.t1)).data  # un lecteur peut consulter
        self.assertEqual((data["total"], [e["user"] for e in data["entries"]].count("alice")), (120, 1))

    def test_validation(self):
        for bad in ({"minutes": 0}, {"minutes": 1441}, {"minutes": "abc"}, {}, {"minutes": -5}):
            self.assertEqual(self.as_(self.alice).post(self.url(self.t1), bad, format="json").status_code, 400, bad)
        future = (date.today() + timedelta(days=5)).isoformat()
        self.assertEqual(self.as_(self.alice).post(self.url(self.t1), {"minutes": 10, "day": future}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.alice).post(self.url(self.t1), {"minutes": 10, "day": "2001-01-01"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.alice).post(self.url(self.t1), {"minutes": 10, "day": "hier"}, format="json").status_code, 400)

    def test_notes_are_truncated(self):
        r = self.as_(self.alice).post(self.url(self.t1), {"minutes": 5, "note": "x" * 500}, format="json")
        self.assertEqual(len(r.data["note"]), 200)

    def test_delete_own_entry_but_not_others_except_the_owner(self):
        mine = self.as_(self.bob).post(self.url(self.t1), {"minutes": 10}, format="json").data
        self.assertEqual(self.as_(self.viewer).delete(self.url(self.t1, f"{mine['id']}/")).status_code, 403)
        carol_like = User.objects.create_user("carol", password="pw-test-123")
        Membership.objects.create(project=self.project, user=carol_like, role="member")
        self.assertEqual(self.as_(carol_like).delete(self.url(self.t1, f"{mine['id']}/")).status_code, 403)
        self.assertEqual(self.as_(self.alice).delete(self.url(self.t1, f"{mine['id']}/")).status_code, 204)  # propriétaire
        mine2 = self.as_(self.bob).post(self.url(self.t1), {"minutes": 10}, format="json").data
        self.assertEqual(self.as_(self.bob).delete(self.url(self.t1, f"{mine2['id']}/")).status_code, 204)
        self.assertEqual(self.as_(self.dave).delete(self.url(self.t1, f"{mine2['id']}/")).status_code, 404)

    def test_total_is_exposed_on_tasks_and_ignores_running_timers(self):
        self.as_(self.alice).post(self.url(self.t1), {"minutes": 45}, format="json")
        self.client.post(self.url(self.t1, "start/"))  # chrono en cours : pas encore compté
        rows = {t["title"]: t["time_minutes"] for t in self.client.get(f"/api/projects/{self.project.pk}/tasks/").data}
        self.assertEqual(rows, {"T1": 45, "T2": 0})
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/tasks/{self.t1.pk}/").data["time_minutes"], 45)

    def test_the_task_list_does_not_multiply_queries_with_time_entries(self):
        for _ in range(8):
            self.as_(self.alice).post(self.url(self.t1), {"minutes": 5}, format="json")
        with self.assertNumQueries(4):  # projet, rôle, tâches (avec le total du temps), dépendances : indépendant du nombre de saisies
            self.client.get(f"/api/projects/{self.project.pk}/tasks/")

    def test_deleting_a_user_keeps_the_time_signed_nobody(self):
        self.as_(self.bob).post(self.url(self.t1), {"minutes": 25}, format="json")
        root = User.objects.create_user("root", password="pw-test-123", is_staff=True)
        admin_services.delete_user(root, self.bob)
        e = TimeEntry.objects.get()
        self.assertEqual((e.minutes, e.user), (25, None))
        self.assertEqual(self.as_(self.alice).get(self.url(self.t1)).data["entries"][0]["user"], None)

    def test_deleting_the_task_deletes_its_time(self):
        self.as_(self.alice).post(self.url(self.t1), {"minutes": 25}, format="json")
        self.t1.delete()
        self.assertEqual(TimeEntry.objects.count(), 0)


class ReportTests(TimeCase):
    def test_report_by_member_task_and_day(self):
        today = date.today()
        mk = lambda u, t, d, m: TimeEntry.objects.create(user=u, task=t, day=d, minutes=m)
        mk(self.alice, self.t1, today, 60)
        mk(self.alice, self.t2, today - timedelta(days=1), 30)
        mk(self.bob, self.t1, today - timedelta(days=2), 120)
        mk(self.bob, self.t1, today - timedelta(days=60), 999)  # hors des 30 derniers jours
        TimeEntry.objects.create(user=self.bob, task=self.t1, day=today, started_at=timezone.now())  # chrono en cours : exclu
        data = self.as_(self.viewer).get(f"/api/projects/{self.project.pk}/time-report/").data
        self.assertEqual(data["total"], 210)
        self.assertEqual([(r["user"], r["minutes"]) for r in data["by_member"]], [("bob", 120), ("alice", 90)])
        self.assertEqual([(r["title"], r["minutes"]) for r in data["by_task"]], [("T1", 180), ("T2", 30)])
        self.assertEqual(len(data["by_day"]), 30)
        self.assertEqual(data["by_day"][-1]["minutes"], 60)

    def test_period_and_rights(self):
        base = f"/api/projects/{self.project.pk}/time-report/"
        self.assertEqual(self.as_(self.alice).get(base, {"from": "2026-10-10", "to": "2026-10-01"}).status_code, 400)
        self.assertEqual(self.as_(self.alice).get(base, {"from": "2020-01-01", "to": "2026-10-01"}).status_code, 400)
        self.assertEqual(self.as_(self.alice).get(base, {"from": "xx"}).status_code, 400)
        self.assertEqual(self.as_(self.dave).get(base).status_code, 404)

    def test_other_projects_never_leak_into_the_report(self):
        other = create_project(self.alice, "Autre")
        t = Task.objects.create(project=other, title="Secret")
        TimeEntry.objects.create(user=self.alice, task=t, day=date.today(), minutes=500)
        data = self.as_(self.alice).get(f"/api/projects/{self.project.pk}/time-report/").data
        self.assertEqual(data["total"], 0)
