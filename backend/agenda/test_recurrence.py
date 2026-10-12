from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model

from accounts.models import Profile
from projects.models import Membership
from projects.services import create_project

from .models import Event, EventSkip, Invitation
from .services import occurrences
from .tests import CalendarTestCase

User = get_user_model()
PARIS = ZoneInfo("Europe/Paris")


def calendar(case, user, first, last, **q):
    return case.as_(user).get("/api/calendar/", {"from": first, "to": last, **q}).data


def local(d, h=9, m=0, tz=PARIS):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=tz)


class RecurrenceTests(CalendarTestCase):
    def series(self, recurrence, start="2026-10-05T09:00", end="2026-10-05T10:00", **extra):
        res = self.event(starts_at=start, ends_at=end, recurrence=recurrence, **extra)
        self.assertEqual(res.status_code, 201, res.data)
        return res.data

    def starts(self, first, last, user=None):
        data = calendar(self, user or self.alice, first, last)
        return [e["occurrence_day"] or e["starts_at"][:10] for e in data["events"]]

    def test_daily_weekdays_weekly_monthly_expansion(self):
        self.series("daily")
        self.assertEqual(len(self.starts("2026-10-05", "2026-10-11")), 7)
        Event.objects.all().delete()
        self.series("weekdays")
        self.assertEqual(self.starts("2026-10-05", "2026-10-11"), [f"2026-10-{d:02d}" for d in range(5, 10)])  # pas de week-end
        Event.objects.all().delete()
        self.series("weekly")
        self.assertEqual(self.starts("2026-10-01", "2026-10-31"), ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"])
        Event.objects.all().delete()
        self.series("monthly", start="2026-01-31T09:00", end="2026-01-31T10:00")
        self.assertEqual(self.starts("2026-01-25", "2026-02-28"), ["2026-01-31"])  # le 31 saute février (28 j), jamais décalé en silence
        self.assertEqual(self.starts("2026-03-01", "2026-03-31"), ["2026-03-31"])
        self.assertEqual(self.starts("2026-04-01", "2026-05-31"), ["2026-05-31"])  # ... et avril (30 j)

    def test_nothing_before_the_first_occurrence_and_after_the_end(self):
        self.series("daily", start="2026-10-10T09:00", end="2026-10-10T10:00", recurrence_until="2026-10-12")
        self.assertEqual(self.starts("2026-10-05", "2026-10-20"), ["2026-10-10", "2026-10-11", "2026-10-12"])
        self.assertEqual(self.starts("2026-10-13", "2026-10-20"), [])

    def test_a_series_is_bounded_to_three_years_without_end(self):
        self.series("weekly", start="2026-10-05T09:00", end="2026-10-05T10:00")
        self.assertEqual(self.starts("2030-10-05", "2030-10-11"), [])  # au-delà de l'horizon de 3 ans
        self.assertEqual(len(self.starts("2028-10-02", "2028-10-08")), 1)

    def test_range_in_the_far_future_is_fast_and_exact(self):
        self.series("weekly", start="2026-10-05T09:00", end="2026-10-05T10:00")
        got = self.starts("2028-10-02", "2028-10-08")
        self.assertEqual(got, ["2028-10-02"])  # lundi, 104 semaines plus tard

    def test_wall_clock_time_is_kept_across_daylight_saving(self):
        self.series("weekly", start="2026-10-19T09:00", end="2026-10-19T10:00")
        data = calendar(self, self.alice, "2026-10-19", "2026-11-02")
        hours = [datetime.fromisoformat(e["starts_at"]).astimezone(PARIS).hour for e in data["events"]]
        self.assertEqual(hours, [9, 9, 9])  # 9 h à Paris le 19 oct. (été), le 26 oct. (hiver) et le 2 nov.
        utc = [datetime.fromisoformat(e["starts_at"]).utcoffset() for e in data["events"]]
        self.assertEqual(utc[0], timedelta(hours=2))
        self.assertEqual(utc[1], timedelta(hours=1))

    def test_recurrence_in_a_foreign_timezone_keeps_that_wall_time(self):
        self.series("daily", start="2026-10-05T09:00", end="2026-10-05T10:00", timezone="Asia/Tokyo")
        data = calendar(self, self.alice, "2026-10-05", "2026-10-06")
        # 9 h à Tokyo = 02 h à Paris (été) : deux occurrences à 02:00 et 02:00
        self.assertEqual({datetime.fromisoformat(e["starts_at"]).astimezone(PARIS).hour for e in data["events"]}, {2})

    def test_occurrences_carry_the_series_times_for_editing(self):
        self.series("weekly")
        occ = calendar(self, self.alice, "2026-10-12", "2026-10-18")["events"][0]
        self.assertEqual(occ["occurrence_day"], "2026-10-12")
        self.assertTrue(occ["series_starts_at"].startswith("2026-10-05"))
        self.assertTrue(occ["starts_at"].startswith("2026-10-12"))

    def test_moving_the_series_moves_every_occurrence(self):
        e = self.series("weekly")
        self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"starts_at": "2026-10-06T14:00", "ends_at": "2026-10-06T15:00"}, format="json")
        self.assertEqual(self.starts("2026-10-12", "2026-10-18"), ["2026-10-13"])

    def test_skipping_one_occurrence_keeps_the_rest(self):
        e = self.series("daily")
        self.assertEqual(self.as_(self.alice).post(f"/api/events/{e['id']}/skip/", {"day": "2026-10-07"}, format="json").status_code, 204)
        days = self.starts("2026-10-05", "2026-10-09")
        self.assertEqual(days, ["2026-10-05", "2026-10-06", "2026-10-08", "2026-10-09"])
        self.assertEqual(self.as_(self.alice).post(f"/api/events/{e['id']}/skip/", {"day": "2026-10-07"}, format="json").status_code, 204)  # idempotent

    def test_skip_validation_and_rights(self):
        e = self.series("weekly")
        url = f"/api/events/{e['id']}/skip/"
        self.assertEqual(self.as_(self.alice).post(url, {"day": "2026-10-06"}, format="json").status_code, 400)  # pas une occurrence
        self.assertEqual(self.as_(self.alice).post(url, {"day": "nimporte"}, format="json").status_code, 400)
        single = self.event().data
        self.assertEqual(self.as_(self.alice).post(f"/api/events/{single['id']}/skip/", {"day": "2026-10-12"}, format="json").status_code, 400)
        shared = self.event(project=self.project.pk, recurrence="daily").data
        self.assertEqual(self.as_(self.carol).post(f"/api/events/{shared['id']}/skip/", {"day": "2026-10-12"}, format="json").status_code, 403)

    def test_deleting_the_series_deletes_everything(self):
        e = self.series("daily")
        self.as_(self.alice).delete(f"/api/events/{e['id']}/")
        self.assertEqual(self.starts("2026-10-05", "2026-10-11"), [])

    def test_validation(self):
        self.assertEqual(self.event(recurrence="hourly").status_code, 400)
        self.assertEqual(self.event(starts_at="2026-10-05T09:00", ends_at="2026-10-06T10:00", recurrence="daily").status_code, 400)  # > 1 jour
        self.assertEqual(self.event(recurrence="daily", recurrence_until="2026-10-01").status_code, 400)

    def test_a_series_is_visible_to_project_members_only(self):
        self.series("daily", project=self.project.pk)
        self.assertEqual(len(self.starts("2026-10-12", "2026-10-12", self.bob)), 1)
        dave = User.objects.create_user("dave", password="pw-test-123")
        self.assertEqual(self.starts("2026-10-12", "2026-10-12", dave), [])

    def test_a_recurring_event_whose_first_date_is_before_the_range_still_shows(self):
        self.series("weekly", start="2026-01-05T09:00", end="2026-01-05T10:00")
        self.assertEqual(self.starts("2026-10-05", "2026-10-11"), ["2026-10-05"])

    def test_engine_unit_midnight_crossing(self):
        e = Event.objects.create(creator=self.alice, title="Nuit", starts_at=local(date(2026, 10, 5), 22), ends_at=local(date(2026, 10, 6), 1),
                                 timezone="Europe/Paris", recurrence="daily")
        got = occurrences(e, local(date(2026, 10, 6), 0), local(date(2026, 10, 6), 2))
        self.assertEqual([o[2] for o in got], [date(2026, 10, 5)])  # l'occurrence du 5 déborde sur le 6


class InvitationTests(CalendarTestCase):
    def invite(self, ids, user=None, **extra):
        return self.event(user or self.alice, attendees=ids, **extra)

    def test_invitees_see_the_event_and_are_notified(self):
        res = self.invite([self.bob.pk], title="Point")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual([(i["username"], i["status"]) for i in res.data["invitees"]], [("bob", "invited")])
        ev = calendar(self, self.bob, "2026-10-12", "2026-10-12")["events"]
        self.assertEqual((len(ev), ev[0]["my_status"], ev[0]["can_edit"]), (1, "invited", False))
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        rows = self.as_(self.bob).get("/api/notifications/").data
        self.assertEqual((rows[0]["type"], rows[0]["title"], rows[0]["author"], rows[0]["status"]), ("invite", "Point", "alice", "invited"))

    def test_the_organizer_is_organizer_and_not_invited_to_their_own_event(self):
        res = self.invite([self.alice.pk, self.bob.pk])
        self.assertEqual([i["username"] for i in res.data["invitees"]], ["bob"])
        self.assertEqual(res.data["my_status"], "organizer")

    def test_rsvp_updates_status_and_marks_the_notification_seen(self):
        e = self.invite([self.bob.pk]).data
        res = self.as_(self.bob).post(f"/api/events/{e['id']}/rsvp/", {"status": "accepted"}, format="json")
        self.assertEqual((res.status_code, res.data["my_status"]), (200, "accepted"))
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 0)
        seen_by_organizer = self.as_(self.alice).get(f"/api/events/{e['id']}/").data["invitees"]
        self.assertEqual(seen_by_organizer[0]["status"], "accepted")
        self.as_(self.bob).post(f"/api/events/{e['id']}/rsvp/", {"status": "declined"}, format="json")
        self.assertEqual(self.as_(self.alice).get(f"/api/events/{e['id']}/").data["invitees"][0]["status"], "declined")

    def test_rsvp_rules(self):
        e = self.invite([self.bob.pk]).data
        url = f"/api/events/{e['id']}/rsvp/"
        self.assertEqual(self.as_(self.bob).post(url, {"status": "maybe"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.bob).post(url, {"status": "invited"}, format="json").status_code, 400)
        self.assertEqual(self.as_(self.alice).post(url, {"status": "accepted"}, format="json").status_code, 403)  # l'organisateur n'est pas invité
        dave = User.objects.create_user("dave", password="pw-test-123")
        self.assertEqual(self.as_(dave).post(url, {"status": "accepted"}, format="json").status_code, 404)

    def test_personal_event_invitees_must_be_colleagues(self):
        dave = User.objects.create_user("dave", password="pw-test-123")
        self.assertEqual(self.invite([dave.pk]).status_code, 400)
        self.assertEqual(self.invite([99999]).status_code, 400)
        self.assertEqual(self.invite([self.carol.pk]).status_code, 201)  # collègue (lecteur du même projet)

    def test_project_event_invitees_must_be_members_of_that_project(self):
        other = User.objects.create_user("erin", password="pw-test-123")
        create_project(other, "Ailleurs")
        self.assertEqual(self.invite([other.pk], project=self.project.pk).status_code, 400)
        self.assertEqual(self.invite([self.bob.pk], project=self.project.pk).status_code, 201)

    def test_inactive_users_cannot_be_invited(self):
        self.bob.is_active = False
        self.bob.save()
        self.assertEqual(self.invite([self.bob.pk]).status_code, 400)

    def test_updating_attendees_adds_and_removes(self):
        e = self.invite([self.bob.pk]).data
        self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"attendees": [self.carol.pk]}, format="json")
        self.assertEqual([i["username"] for i in self.as_(self.alice).get(f"/api/events/{e['id']}/").data["invitees"]], ["carol"])
        self.assertEqual(self.as_(self.bob).get(f"/api/events/{e['id']}/").status_code, 404)  # retiré : ne voit plus rien
        self.as_(self.alice).patch(f"/api/events/{e['id']}/", {"title": "Renommé"}, format="json")  # sans `attendees` : inchangé
        self.assertEqual(len(self.as_(self.alice).get(f"/api/events/{e['id']}/").data["invitees"]), 1)

    def test_an_invitee_cannot_edit_delete_or_reinvite(self):
        e = self.invite([self.bob.pk]).data
        self.assertEqual(self.as_(self.bob).patch(f"/api/events/{e['id']}/", {"title": "x"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.bob).delete(f"/api/events/{e['id']}/").status_code, 403)
        self.assertEqual(self.as_(self.bob).patch(f"/api/events/{e['id']}/", {"attendees": [self.carol.pk]}, format="json").status_code, 403)

    def test_deleting_the_event_removes_invitations(self):
        e = self.invite([self.bob.pk]).data
        self.as_(self.alice).delete(f"/api/events/{e['id']}/")
        self.assertEqual(Invitation.objects.count(), 0)
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 0)

    def test_invitations_can_be_marked_seen_individually_or_all(self):
        a, b = self.invite([self.bob.pk], title="A").data, self.invite([self.bob.pk], title="B").data
        rows = self.as_(self.bob).get("/api/notifications/").data
        self.as_(self.bob).post("/api/notifications/", {"invitations": [rows[0]["id"]]}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)
        self.as_(self.bob).post("/api/notifications/", {"all": True}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 0)

    def test_nobody_marks_someone_elses_invitations(self):
        self.invite([self.bob.pk])
        row = self.as_(self.bob).get("/api/notifications/").data[0]
        self.as_(self.carol).post("/api/notifications/", {"invitations": [row["id"]]}, format="json")
        self.assertEqual(self.as_(self.bob).get("/api/chat/summary/").data["unread_notifications"], 1)

    def test_contacts_endpoint(self):
        self.assertEqual([u["username"] for u in self.as_(self.alice).get("/api/calendar/contacts/").data], ["bob", "carol"])

    def test_recurring_invited_event_shows_for_the_invitee_with_their_status(self):
        self.invite([self.bob.pk], recurrence="daily")
        ev = calendar(self, self.bob, "2026-10-12", "2026-10-12")["events"]
        self.assertEqual([(e["my_status"], e["occurrence_day"]) for e in ev], [("invited", "2026-10-12")])
