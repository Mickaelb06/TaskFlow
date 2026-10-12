from datetime import date, datetime, timezone as utc
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from accounts.models import Profile
from projects.models import Membership
from projects.services import create_project
from tasks.models import Task

from .models import Event

User = get_user_model()
PW = "pw-test-123"


def utc_dt(*args):
    return datetime(*args, tzinfo=utc.utc)


class CalendarTestCase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password=PW)
        self.bob = User.objects.create_user("bob", password=PW)
        self.carol = User.objects.create_user("carol", password=PW)
        self.project = create_project(self.alice, "Site")
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        Membership.objects.create(project=self.project, user=self.carol, role="viewer")

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def event(self, user=None, **kw):
        data = {"title": "Réunion", "starts_at": "2026-10-12T14:00", "ends_at": "2026-10-12T15:00", **kw}
        return self.as_(user or self.alice).post("/api/events/", data)


class TimezoneTests(CalendarTestCase):
    def test_default_timezone_is_paris_and_profile_is_created_on_first_read(self):
        res = self.as_(self.alice).get("/api/me/")
        self.assertEqual((res.data["timezone"], res.data["secondary_timezone"]), ("Europe/Paris", ""))
        self.assertTrue(Profile.objects.filter(user=self.alice).exists())

    def test_user_can_change_timezones_but_not_their_rights(self):
        res = self.as_(self.alice).patch("/api/me/", {"timezone": "Asia/Tokyo", "secondary_timezone": "America/New_York", "is_staff": True})
        self.assertEqual(res.status_code, 200)
        self.assertEqual((res.data["timezone"], res.data["secondary_timezone"], res.data["is_staff"]), ("Asia/Tokyo", "America/New_York", False))
        self.assertEqual(self.as_(self.alice).patch("/api/me/", {"secondary_timezone": ""}, format="json").data["secondary_timezone"], "")

    def test_unknown_timezone_is_rejected(self):
        for bad in ("Mars/Olympus", "../etc/passwd", "UTC+2", ""):
            self.assertEqual(self.as_(self.alice).patch("/api/me/", {"timezone": bad}, format="json").status_code, 400, bad)
        self.assertEqual(self.as_(self.alice).patch("/api/me/", {"secondary_timezone": "Nope/Nope"}).status_code, 400)

    def test_a_wall_time_is_read_in_the_event_timezone(self):
        # 14 h à Tokyo (UTC+9, pas d'heure d'été) = 05 h UTC
        res = self.event(timezone="Asia/Tokyo")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(Event.objects.get().starts_at, utc_dt(2026, 10, 12, 5, 0))
        self.assertEqual(res.data["timezone"], "Asia/Tokyo")

    def test_without_timezone_the_wall_time_is_read_in_the_profile_timezone(self):
        Profile.objects.update_or_create(user=self.alice, defaults={"timezone": "America/New_York"})
        self.event()  # 14 h à New York, en EDT (UTC-4) le 12 octobre 2026 = 18 h UTC
        self.assertEqual(Event.objects.get().starts_at, utc_dt(2026, 10, 12, 18, 0))

    def test_explicit_offset_wins_over_timezone(self):
        self.event(starts_at="2026-10-12T14:00:00+02:00", ends_at="2026-10-12T15:00:00+02:00", timezone="Asia/Tokyo")
        self.assertEqual(Event.objects.get().starts_at, utc_dt(2026, 10, 12, 12, 0))

    def test_daylight_saving_changes_the_utc_hour(self):
        # Paris : UTC+2 jusqu'au 25 octobre 2026, UTC+1 ensuite
        self.event(starts_at="2026-10-24T09:00", ends_at="2026-10-24T10:00")
        self.event(starts_at="2026-10-26T09:00", ends_at="2026-10-26T10:00")
        hours = [e.starts_at.hour for e in Event.objects.order_by("starts_at")]
        self.assertEqual(hours, [7, 8])

    def test_nonexistent_and_repeated_wall_times_do_not_crash(self):
        # 29 mars 2026 : 02:30 n'existe pas à Paris ; 25 octobre 2026 : 02:30 existe deux fois
        self.assertEqual(self.event(starts_at="2026-03-29T02:30", ends_at="2026-03-29T04:00").status_code, 201)
        self.assertEqual(self.event(starts_at="2026-10-25T02:30", ends_at="2026-10-25T04:00").status_code, 201)

    def test_response_can_be_read_in_any_timezone(self):
        res = self.event(timezone="Asia/Tokyo")
        instant = datetime.fromisoformat(res.data["starts_at"])
        self.assertEqual(instant.astimezone(ZoneInfo("Asia/Tokyo")).hour, 14)
        self.assertEqual(instant.astimezone(ZoneInfo("America/New_York")).hour, 1)

    def test_garbage_dates_and_zones_are_400(self):
        self.assertEqual(self.event(starts_at="demain").status_code, 400)
        self.assertEqual(self.event(timezone="Mars/Olympus").status_code, 400)


class EventRuleTests(CalendarTestCase):
    def test_end_must_follow_start_and_duration_is_bounded(self):
        self.assertEqual(self.event(ends_at="2026-10-12T14:00").status_code, 400)
        self.assertEqual(self.event(ends_at="2026-10-12T13:00").status_code, 400)
        self.assertEqual(self.event(ends_at="2026-12-12T13:00").status_code, 400)

    def test_patch_revalidates_the_range_with_the_stored_values(self):
        e = self.event().data
        self.assertEqual(self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"ends_at": "2026-10-12T13:00"}).status_code, 400)
        ok = self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"ends_at": "2026-10-12T17:30", "title": "Atelier"})
        self.assertEqual((ok.status_code, ok.data["title"]), (200, "Atelier"))

    def test_patch_keeps_the_event_timezone_when_only_a_time_is_sent(self):
        e = self.event(timezone="Asia/Tokyo").data
        self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"starts_at": "2026-10-12T13:00"})
        self.assertEqual(Event.objects.get().starts_at, utc_dt(2026, 10, 12, 4, 0))

    def test_personal_event_is_private(self):
        e = self.event().data
        self.assertIsNone(e["project"])
        self.assertEqual(self.as_(self.bob).get("/api/events/").data, [])
        self.assertEqual(self.as_(self.bob).get(f"/api/events/{e['id']}/").status_code, 404)
        self.assertEqual(self.as_(self.bob).delete(f"/api/events/{e['id']}/").status_code, 404)

    def test_project_events_are_shared_with_members_and_hidden_from_others(self):
        e = self.event(project=self.project.pk).data
        self.assertEqual(len(self.as_(self.bob).get("/api/events/").data), 1)
        self.assertEqual(len(self.as_(self.carol).get("/api/events/").data), 1)
        dave = User.objects.create_user("dave", password=PW)
        self.assertEqual(self.as_(dave).get("/api/events/").data, [])
        self.assertEqual(self.as_(dave).get(f"/api/events/{e['id']}/").status_code, 404)

    def test_viewer_reads_but_cannot_write_project_events(self):
        e = self.event(project=self.project.pk).data
        self.assertFalse(self.as_(self.carol).get(f"/api/events/{e['id']}/").data["can_edit"])
        self.assertEqual(self.event(self.carol, project=self.project.pk).status_code, 403)
        self.assertEqual(self.as_(self.carol).patch(f"/api/events/{e['id']}/", {"title": "x"}).status_code, 403)
        self.assertEqual(self.as_(self.carol).delete(f"/api/events/{e['id']}/").status_code, 403)
        self.assertTrue(self.as_(self.bob).get(f"/api/events/{e['id']}/").data["can_edit"])
        self.assertEqual(self.as_(self.bob).patch(f"/api/events/{e['id']}/", {"title": "ok"}).status_code, 200)

    def test_cannot_use_a_project_you_do_not_belong_to(self):
        dave = User.objects.create_user("dave", password=PW)
        self.assertEqual(self.event(dave, project=self.project.pk).status_code, 400)
        e = self.event().data  # événement personnel d'alice
        self.assertEqual(self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"project": 999}).status_code, 400)

    def test_cannot_move_an_event_into_a_project_where_one_is_a_viewer(self):
        e = self.event(self.carol).data
        self.assertEqual(self.as_(self.carol).patch(f"/api/events/{e['id']}/", {"project": self.project.pk}).status_code, 403)

    def test_deleting_the_project_removes_its_events_and_deleting_a_user_removes_personal_ones(self):
        self.event(project=self.project.pk)
        self.event(self.bob)
        self.project.delete()
        self.assertEqual(Event.objects.count(), 1)
        from accounts import admin_services as svc
        admin = User.objects.create_user("root", password=PW, is_staff=True)
        svc.delete_user(admin, self.bob)
        self.assertEqual(Event.objects.count(), 0)

    def test_unauthenticated_is_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/events/").status_code, 401)
        self.assertEqual(self.client.get("/api/calendar/?from=2026-10-12&to=2026-10-18").status_code, 401)


class CalendarViewTests(CalendarTestCase):
    URL = "/api/calendar/?from=2026-10-12&to=2026-10-18"

    def setUp(self):
        super().setUp()
        self.t1 = Task.objects.create(project=self.project, title="Maquette", start_date=date(2026, 10, 13), due_date=date(2026, 10, 15), assignee=self.alice)
        self.t2 = Task.objects.create(project=self.project, title="Hors période", start_date=date(2026, 11, 2), due_date=date(2026, 11, 3))
        self.t3 = Task.objects.create(project=self.project, title="Longue", start_date=date(2026, 10, 1), due_date=date(2026, 10, 30), assignee=self.bob)
        Task.objects.create(project=self.project, title="Sans date")

    def test_returns_tasks_overlapping_the_period_and_events_in_it(self):
        self.event(project=self.project.pk, starts_at="2026-10-14T10:00", ends_at="2026-10-14T11:00")
        self.event(starts_at="2026-11-14T10:00", ends_at="2026-11-14T11:00")
        data = self.as_(self.alice).get(self.URL).data
        self.assertEqual(data["timezone"], "Europe/Paris")
        self.assertEqual(sorted(t["title"] for t in data["tasks"]), ["Longue", "Maquette"])
        self.assertEqual([e["title"] for e in data["events"]], ["Réunion"])
        self.assertEqual(data["tasks"][0]["project_name"], "Site")

    def test_days_are_those_of_the_profile_timezone(self):
        # 23 h 30 à Paris le dimanche 18 = 21 h 30 UTC : dans la semaine à Paris, mais le lundi 19 à Tokyo
        self.event(starts_at="2026-10-18T23:30", ends_at="2026-10-18T23:45")
        self.assertEqual(len(self.as_(self.alice).get(self.URL).data["events"]), 1)
        Profile.objects.filter(user=self.alice).update(timezone="Asia/Tokyo")
        self.assertEqual(self.as_(self.alice).get(self.URL).data["events"], [])
        self.assertEqual(len(self.as_(self.alice).get("/api/calendar/?from=2026-10-19&to=2026-10-19").data["events"]), 1)

    def test_event_crossing_midnight_shows_on_both_days(self):
        self.event(starts_at="2026-10-14T22:00", ends_at="2026-10-15T02:00")
        for day in ("2026-10-14", "2026-10-15"):
            self.assertEqual(len(self.as_(self.alice).get(f"/api/calendar/?from={day}&to={day}").data["events"]), 1, day)
        self.assertEqual(self.as_(self.alice).get("/api/calendar/?from=2026-10-16&to=2026-10-16").data["events"], [])

    def test_filters_by_project_and_by_assignee(self):
        other = create_project(self.alice, "Perso")
        Task.objects.create(project=other, title="Courses", due_date=date(2026, 10, 14))
        titles = lambda d: sorted(t["title"] for t in d["tasks"])
        self.assertEqual(titles(self.as_(self.alice).get(self.URL + f"&project={other.pk}").data), ["Courses"])
        self.assertEqual(titles(self.as_(self.alice).get(self.URL + "&mine=1").data), ["Maquette"])

    def test_never_leaks_other_peoples_projects_or_events(self):
        dave = User.objects.create_user("dave", password=PW)
        data = self.as_(dave).get(self.URL).data
        self.assertEqual((data["tasks"], data["events"]), ([], []))
        self.assertEqual(self.as_(dave).get(self.URL + f"&project={self.project.pk}").status_code, 404)

    def test_bad_ranges_are_400(self):
        for q in ("", "?from=2026-10-12", "?from=abc&to=2026-10-18", "?from=2026-10-18&to=2026-10-12", "?from=2026-01-01&to=2026-12-31"):
            self.assertEqual(self.as_(self.alice).get("/api/calendar/" + q).status_code, 400, q)
