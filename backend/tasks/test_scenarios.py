from datetime import date, timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from projects.models import Membership
from projects.services import create_project

from . import planning
from .models import Task

User = get_user_model()
MON = date(2026, 10, 12)  # un lundi


class ScenarioCase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")
        self.viewer = User.objects.create_user("vera", password="pw-test-123")
        self.dave = User.objects.create_user("dave", password="pw-test-123")
        self.project = create_project(self.alice, "P")
        Membership.objects.create(project=self.project, user=self.bob, role="member")
        Membership.objects.create(project=self.project, user=self.viewer, role="viewer")

    def make(self, title, a, b, deps=(), **kw):
        t = Task.objects.create(project=self.project, title=title, start_date=a, due_date=b, **kw)
        t.dependencies.set(deps)
        return t

    def get(self, user, path):
        self.client.force_authenticate(user)
        return self.client.get(f"/api/projects/{self.project.pk}/{path}")


class SimulationTests(ScenarioCase):
    def test_a_critical_task_pushes_the_end_and_an_isolated_short_one_does_not(self):
        a = self.make("A", MON, MON + timedelta(days=4))                            # 12-16
        b = self.make("B", MON + timedelta(days=5), MON + timedelta(days=9), [a])    # 17-21 : fin du projet
        c = self.make("Isolée", MON, MON + timedelta(days=2))                        # 12-14, marge de 7 jours
        res = planning.delay_simulation(self.project, 3, today=MON)
        rows = {r["title"]: r for r in res["tasks"]}
        self.assertEqual((rows["A"]["end_delay_days"], rows["A"]["pushed"], rows["A"]["critical"]), (3, 1, True))
        self.assertEqual((rows["B"]["end_delay_days"], rows["B"]["pushed"]), (3, 0))
        self.assertEqual((rows["Isolée"]["end_delay_days"], rows["Isolée"]["critical"]), (0, False))
        self.assertEqual(res["safe"], 1)
        self.assertEqual(res["forecast_end"], MON + timedelta(days=9))
        self.assertEqual([r["title"] for r in res["tasks"]][-1], "Isolée")  # les plus sûres en dernier

    def test_a_slack_task_becomes_critical_when_the_delay_exceeds_its_slack(self):
        self.make("Longue", MON, MON + timedelta(days=9))                 # 10 jours : fin du projet
        self.make("Courte", MON, MON + timedelta(days=2))                 # marge de 7 jours
        small = {r["title"]: r["end_delay_days"] for r in planning.delay_simulation(self.project, 5, today=MON)["tasks"]}
        big = {r["title"]: r["end_delay_days"] for r in planning.delay_simulation(self.project, 10, today=MON)["tasks"]}
        self.assertEqual(small["Courte"], 0)
        self.assertEqual(big["Courte"], 3)  # 3 + 10 jours : dépasse de 3 jours la fin de « Longue »

    def test_done_and_unplanned_tasks_are_ignored(self):
        self.make("Fini", MON, MON + timedelta(days=3), status="done")
        Task.objects.create(project=self.project, title="Sans date")
        self.assertEqual(planning.delay_simulation(self.project, 3, today=MON)["tasks"], [])

    def test_late_tasks_already_push_the_forecast_and_the_simulation_adds_to_it(self):
        self.make("En retard", MON - timedelta(days=10), MON - timedelta(days=5), status="doing")
        res = planning.delay_simulation(self.project, 2, today=MON)
        self.assertEqual(res["forecast_end"], MON)
        self.assertEqual(res["tasks"][0]["end_delay_days"], 2)

    def test_working_day_projects_count_in_working_days(self):
        self.project.skip_weekends = True
        self.project.save()
        a = self.make("A", date(2026, 10, 15), date(2026, 10, 16))                 # jeu-ven
        self.make("B", date(2026, 10, 19), date(2026, 10, 19), [a])                # lundi
        res = planning.delay_simulation(self.project, 3, today=date(2026, 10, 12))
        self.assertEqual(res["unit"], "jours ouvrés")
        self.assertEqual(res["tasks"][0]["end_delay_days"], 3)  # 3 jours ouvrés (et non 3 jours calendaires)

    def test_api_validation_and_rights(self):
        self.make("A", MON, MON + timedelta(days=2))
        self.assertEqual(self.get(self.alice, "simulate/?delay=3").status_code, 200)
        self.assertEqual(self.get(self.viewer, "simulate/").status_code, 200)  # un lecteur peut consulter
        for bad in ("0", "61", "abc", "-2"):
            self.assertEqual(self.get(self.alice, f"simulate/?delay={bad}").status_code, 400, bad)
        self.assertEqual(self.get(self.dave, "simulate/").status_code, 404)  # étranger
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/simulate/").status_code, 401)

    def test_dependency_cycle_is_a_clean_400(self):
        a = self.make("A", MON, MON + timedelta(days=1))
        b = self.make("B", MON + timedelta(days=2), MON + timedelta(days=3), [a])
        a.dependencies.set([b])
        self.assertEqual(self.get(self.alice, "simulate/").status_code, 400)


class WorkloadTests(ScenarioCase):
    def test_load_per_member_and_week(self):
        self.make("T1", MON, MON + timedelta(days=4), assignee=self.alice)                       # 5 jours : 100 %
        self.make("T2", MON, MON + timedelta(days=4), assignee=self.alice)                       # en parallèle : 200 %
        self.make("T3", MON + timedelta(days=7), MON + timedelta(days=8), assignee=self.bob)     # semaine suivante : 2 jours = 40 %
        data = planning.workload(self.project, 3, today=MON + timedelta(days=2))
        by = {m["username"]: m["cells"] for m in data["members"]}
        self.assertEqual([c["percent"] for c in by["alice"]], [200, 0, 0])
        self.assertEqual([c["percent"] for c in by["bob"]], [0, 40, 0])
        self.assertEqual(data["weeks"][0]["start"], MON)  # semaine du lundi, quel que soit le jour d'appel

    def test_weekends_do_not_count(self):
        self.make("Long", MON + timedelta(days=3), MON + timedelta(days=9), assignee=self.alice)  # jeu 15 → mer 21 : 5 jours ouvrés
        cells = planning.workload(self.project, 2, today=MON)["members"][0]["cells"]
        self.assertEqual([c["days"] for c in cells], [2, 3])  # jeu-ven, puis lun-mar-mer

    def test_done_unplanned_and_unassigned_tasks_are_ignored(self):
        self.make("Fini", MON, MON + timedelta(days=4), assignee=self.alice, status="done")
        self.make("Libre", MON, MON + timedelta(days=4))
        Task.objects.create(project=self.project, title="Sans date", assignee=self.alice)
        self.assertEqual(planning.workload(self.project, 1, today=MON)["members"][0]["cells"][0]["days"], 0)

    def test_overload_suggests_moving_a_low_priority_todo_to_the_least_loaded_member(self):
        self.make("Urgente", MON, MON + timedelta(days=4), assignee=self.alice, priority=1, status="doing")
        low = self.make("Secondaire", MON, MON + timedelta(days=2), assignee=self.alice, priority=3)
        self.make("Moyenne", MON, MON + timedelta(days=1), assignee=self.alice, priority=2)
        self.make("Petite", MON, MON, assignee=self.bob)
        data = planning.workload(self.project, 1, today=MON)
        self.assertEqual(len(data["suggestions"]), 1)
        s = data["suggestions"][0]
        self.assertEqual((s["task"], s["from"], s["to"]), (low.pk, "alice", "bob"))
        self.assertIn("alice est à", s["reason"])

    def test_no_suggestion_when_nobody_can_absorb_or_when_the_target_is_a_viewer(self):
        self.make("T1", MON, MON + timedelta(days=4), assignee=self.alice, priority=3)
        self.make("T2", MON, MON + timedelta(days=4), assignee=self.alice, priority=3)
        self.make("Plein", MON, MON + timedelta(days=4), assignee=self.bob)  # bob est à 100 % : ne peut rien absorber
        self.assertEqual(planning.workload(self.project, 1, today=MON)["suggestions"], [])
        Task.objects.filter(title="Plein").delete()
        data = planning.workload(self.project, 1, today=MON)
        self.assertEqual([s["to"] for s in data["suggestions"]], ["bob"])  # la lectrice n'est jamais proposée

    def test_started_tasks_are_never_suggested_for_reassignment(self):
        self.make("En cours 1", MON, MON + timedelta(days=4), assignee=self.alice, status="doing")
        self.make("En cours 2", MON, MON + timedelta(days=4), assignee=self.alice, status="doing")
        self.assertEqual(planning.workload(self.project, 1, today=MON)["suggestions"], [])

    def test_api(self):
        self.make("T", MON, MON + timedelta(days=1), assignee=self.alice)
        res = self.get(self.viewer, "workload/?weeks=2")
        self.assertEqual((res.status_code, len(res.data["weeks"]), len(res.data["members"])), (200, 2, 3))
        self.assertEqual(len(self.get(self.alice, "workload/").data["weeks"]), 4)  # défaut
        self.assertEqual(len(self.get(self.alice, "workload/?weeks=99").data["weeks"]), 12)  # borné
        self.assertEqual(self.get(self.alice, "workload/?weeks=x").status_code, 400)
        self.assertEqual(self.get(self.dave, "workload/").status_code, 404)
