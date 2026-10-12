from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from projects.services import create_project

from . import planning, workdays as wd
from .models import Task

User = get_user_model()
D = date  # lundi 5 oct. 2026 … vendredi 9, samedi 10, dimanche 11, lundi 12


class WorkdayHelperTests(APITestCase):
    def test_indices_skip_the_weekend_and_are_monotonic(self):
        mon = D(2026, 10, 5)
        idx = [wd.to_index(mon + timedelta(days=i)) for i in range(8)]  # lun mar mer jeu ven sam dim lun
        self.assertEqual(idx[1:5], [idx[0] + 1, idx[0] + 2, idx[0] + 3, idx[0] + 4])
        self.assertEqual((idx[5], idx[6], idx[7]), (idx[0] + 5, idx[0] + 5, idx[0] + 5))  # sam, dim, lun suivant : même numéro

    def test_round_trip_for_every_weekday_of_ten_years(self):
        day = D(2024, 1, 1)
        for _ in range(3650):
            if day.weekday() < 5:
                self.assertEqual(wd.from_index(wd.to_index(day)), day)
            else:
                self.assertEqual(wd.from_index(wd.to_index(day)).weekday(), 0)  # un week-end devient le lundi suivant
            day += timedelta(days=1)

    def test_helpers(self):
        self.assertEqual(wd.next_workday(D(2026, 10, 10)), D(2026, 10, 12))
        self.assertEqual(wd.next_workday(D(2026, 10, 9)), D(2026, 10, 9))
        self.assertEqual(wd.add_workdays(D(2026, 10, 9), 1), D(2026, 10, 12))
        self.assertEqual(wd.add_workdays(D(2026, 10, 12), -1), D(2026, 10, 9))
        self.assertEqual(wd.add_workdays(D(2026, 10, 5), 10), D(2026, 10, 19))
        self.assertTrue(wd.is_weekend(D(2026, 10, 11)) and not wd.is_weekend(D(2026, 10, 12)))

    def test_year_boundaries_and_leap_days(self):
        self.assertEqual(wd.add_workdays(D(2026, 12, 31), 1), D(2027, 1, 1))  # jeudi → vendredi
        self.assertEqual(wd.add_workdays(D(2024, 2, 28), 2), D(2024, 3, 1))   # 29 fév. 2024 est un jeudi


class WorkdayPlanningTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw-test-123")
        self.project = create_project(self.user, "P")
        self.client.force_authenticate(self.user)

    def make(self, title, a, b, deps=(), **kw):
        t = Task.objects.create(project=self.project, title=title, start_date=a, due_date=b, **kw)
        t.dependencies.set(deps)
        return t

    def patch(self, task, **data):
        res = self.client.patch(f"/api/projects/{self.project.pk}/tasks/{task.pk}/", data, format="json")
        self.assertEqual(res.status_code, 200, res.data)

    def set_workdays(self, on=True):
        self.project.skip_weekends = on
        self.project.save()

    def test_a_successor_starts_on_the_next_working_day(self):
        self.set_workdays()
        a = self.make("A", D(2026, 10, 5), D(2026, 10, 7))
        b = self.make("B", D(2026, 10, 8), D(2026, 10, 9), [a])
        self.patch(a, due_date="2026-10-09")  # A passe à 5 jours : finit vendredi
        b.refresh_from_db()
        self.assertEqual((b.start_date, b.due_date), (D(2026, 10, 12), D(2026, 10, 13)))  # lundi, mardi — pas samedi/dimanche

    def test_the_same_change_in_calendar_days_lands_on_the_weekend(self):
        a = self.make("A", D(2026, 10, 5), D(2026, 10, 7))
        b = self.make("B", D(2026, 10, 8), D(2026, 10, 9), [a])
        self.patch(a, due_date="2026-10-09")
        b.refresh_from_db()
        self.assertEqual((b.start_date, b.due_date), (D(2026, 10, 10), D(2026, 10, 11)))

    def test_a_task_keeps_its_working_duration_across_a_weekend(self):
        self.set_workdays()
        a = self.make("A", D(2026, 10, 5), D(2026, 10, 7))
        b = self.make("B", D(2026, 10, 8), D(2026, 10, 12), [a])  # jeu, ven, lun = 3 jours ouvrés
        self.patch(a, due_date="2026-10-08")  # A finit jeudi : B commence vendredi
        b.refresh_from_db()
        self.assertEqual((b.start_date, b.due_date), (D(2026, 10, 9), D(2026, 10, 13)))  # ven, lun, mar = 3 jours ouvrés

    def test_a_chain_of_three_skips_weekends_everywhere(self):
        self.set_workdays()
        a = self.make("A", D(2026, 10, 5), D(2026, 10, 6))
        b = self.make("B", D(2026, 10, 7), D(2026, 10, 9), [a])
        c = self.make("C", D(2026, 10, 12), D(2026, 10, 13), [b])
        self.patch(a, due_date="2026-10-08")  # A +2 jours : B jeudi→lundi, C mardi→mercredi
        b.refresh_from_db()
        c.refresh_from_db()
        self.assertEqual((b.start_date, b.due_date), (D(2026, 10, 9), D(2026, 10, 13)))
        self.assertEqual((c.start_date, c.due_date), (D(2026, 10, 14), D(2026, 10, 15)))
        self.assertTrue(all(t.start_date.weekday() < 5 and t.due_date.weekday() < 5 for t in (b, c)))

    def test_forecast_end_and_critical_path_use_working_days(self):
        self.set_workdays()
        a = self.make("A", D(2026, 10, 8), D(2026, 10, 12))      # jeu → lun : 5 jours calendaires, 3 ouvrés
        b = self.make("B", D(2026, 10, 13), D(2026, 10, 13), [a])  # mardi : 1 jour
        ids, length = planning.critical_path([a, b], workdays=True)
        self.assertEqual((ids, length), ([a.pk, b.pk], 4))     # 3 + 1 jours ouvrés
        self.assertEqual(planning.critical_path([a, b])[1], 6)  # 5 + 1 jours calendaires
        self.assertEqual(planning.forecast_end([a, b], D(2026, 10, 8), workdays=True), D(2026, 10, 13))

    def test_a_late_task_restarts_on_a_working_day(self):
        self.set_workdays()
        late = self.make("En retard", D(2026, 10, 5), D(2026, 10, 7), status="doing")  # 3 jours ouvrés
        planning.replan(self.project, today=D(2026, 10, 10))  # samedi
        late.refresh_from_db()
        self.assertEqual((late.start_date, late.due_date), (D(2026, 10, 12), D(2026, 10, 14)))

    def test_calendar_projects_are_unchanged(self):
        late = self.make("En retard", D(2026, 10, 5), D(2026, 10, 7), status="doing")
        planning.replan(self.project, today=D(2026, 10, 10))
        late.refresh_from_db()
        self.assertEqual((late.start_date, late.due_date), (D(2026, 10, 10), D(2026, 10, 12)))

    def test_insights_progress_weighs_working_days(self):
        self.set_workdays()
        self.make("Fini", D(2026, 10, 9), D(2026, 10, 12), status="done")  # ven-lun : 2 jours ouvrés
        self.make("Ouvert", D(2026, 10, 13), D(2026, 10, 14))              # 2 jours ouvrés
        self.assertEqual(planning.insights(self.project, D(2026, 10, 13))["progress"], 50)

    def test_the_setting_is_exposed_and_owner_only(self):
        res = self.client.patch(f"/api/projects/{self.project.pk}/", {"skip_weekends": True}, format="json")
        self.assertEqual((res.status_code, res.data["skip_weekends"]), (200, True))
        bob = User.objects.create_user("bob", password="pw-test-123")
        from projects.models import Membership
        Membership.objects.create(project=self.project, user=bob, role="member")
        self.client.force_authenticate(bob)
        self.assertEqual(self.client.patch(f"/api/projects/{self.project.pk}/", {"skip_weekends": False}, format="json").status_code, 403)

    def test_cycles_still_raise_in_working_day_mode(self):
        from django.core.exceptions import ValidationError
        a = self.make("A", D(2026, 10, 5), D(2026, 10, 6))
        b = self.make("B", D(2026, 10, 7), D(2026, 10, 8), [a])
        a.dependencies.set([b])
        with self.assertRaises(ValidationError):
            planning.critical_path([a, b], workdays=True)
