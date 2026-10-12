from datetime import date

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from tasks.models import Task

from . import templates
from .models import Project, ProjectTemplate
from .services import create_project

User = get_user_model()
MON = date(2026, 10, 12)


class TemplateCase(APITestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw-test-123")
        self.bob = User.objects.create_user("bob", password="pw-test-123")

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def from_tpl(self, user, **body):
        return self.as_(user).post("/api/projects/from-template/", body, format="json")


class BuiltinTemplateTests(TemplateCase):
    def test_the_catalog_lists_builtin_then_personal_templates(self):
        rows = self.as_(self.alice).get("/api/templates/").data
        self.assertEqual([r["key"] for r in rows], ["builtin:site-web", "builtin:evenement", "builtin:sprint", "builtin:lancement"])
        self.assertTrue(all(r["builtin"] and r["tasks"] >= 6 for r in rows))
        ProjectTemplate.objects.create(owner=self.alice, name="Le mien", tasks=[])
        ProjectTemplate.objects.create(owner=self.bob, name="Celui de bob", tasks=[])
        keys = [r["name"] for r in self.client.get("/api/templates/").data]
        self.assertEqual(keys[-1], "Le mien")
        self.assertNotIn("Celui de bob", keys)

    def test_every_builtin_creates_a_consistent_project(self):
        for key in templates.BUILTIN:
            res = self.from_tpl(self.alice, template=f"builtin:{key}", start_date="2026-10-12")
            self.assertEqual(res.status_code, 201, key)
            project = Project.objects.get(pk=res.data["id"])
            self.assertEqual((project.owner, res.data["role"]), (self.alice, "owner"))
            tasks = list(project.tasks.prefetch_related("dependencies"))
            self.assertGreaterEqual(len(tasks), 6)
            for t in tasks:
                self.assertLessEqual(t.start_date, t.due_date)
                for dep in t.dependencies.all():  # une tâche ne commence jamais avant la fin de ses prérequis
                    self.assertLess(dep.due_date, t.start_date, f"{key}: {t.title} commence avant la fin de {dep.title}")
                if project.skip_weekends:
                    self.assertTrue(t.start_date.weekday() < 5 and t.due_date.weekday() < 5, (key, t.title))

    def test_dates_follow_the_chosen_start_and_working_days(self):
        res = self.from_tpl(self.alice, template="builtin:sprint", start_date="2026-10-14")  # mercredi
        project = Project.objects.get(pk=res.data["id"])
        self.assertTrue(project.skip_weekends)
        first = project.tasks.get(title="Planification du sprint")
        self.assertEqual((first.start_date, first.due_date), (date(2026, 10, 14), date(2026, 10, 14)))
        second = project.tasks.get(title="Développement — lot 1")
        self.assertEqual(second.start_date, date(2026, 10, 15))
        review = project.tasks.get(title="Revue de sprint")
        self.assertTrue(review.is_milestone)

    def test_a_weekend_start_moves_to_monday_in_working_day_templates(self):
        res = self.from_tpl(self.alice, template="builtin:site-web", start_date="2026-10-10")  # samedi
        first = Project.objects.get(pk=res.data["id"]).tasks.get(title="Cadrage et besoins")
        self.assertEqual(first.start_date, date(2026, 10, 12))

    def test_calendar_day_template_keeps_calendar_days(self):
        res = self.from_tpl(self.alice, template="builtin:evenement", start_date="2026-10-12")
        project = Project.objects.get(pk=res.data["id"])
        self.assertFalse(project.skip_weekends)
        self.assertEqual(project.tasks.get(title="Jour J").start_date, date(2026, 11, 11))  # 30 jours calendaires plus tard

    def test_name_and_defaults(self):
        res = self.from_tpl(self.alice, template="builtin:sprint", name="Sprint 42")
        self.assertEqual(res.data["name"], "Sprint 42")
        res = self.from_tpl(self.alice, template="builtin:sprint")
        self.assertEqual(res.data["name"], "Sprint de 2 semaines")
        self.assertTrue(Project.objects.get(pk=res.data["id"]).tasks.filter(start_date__gte=date.today()).exists())

    def test_the_new_project_is_private_to_its_creator(self):
        res = self.from_tpl(self.alice, template="builtin:sprint")
        self.assertEqual(self.as_(self.bob).get(f"/api/projects/{res.data['id']}/").status_code, 404)

    def test_validation(self):
        self.assertEqual(self.from_tpl(self.alice, template="builtin:inconnu").status_code, 400)
        self.assertEqual(self.from_tpl(self.alice).status_code, 400)
        self.assertEqual(self.from_tpl(self.alice, template="builtin:sprint", start_date="demain").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/projects/from-template/", {"template": "builtin:sprint"}, format="json").status_code, 401)


class PersonalTemplateTests(TemplateCase):
    def build(self, skip=False):
        p = create_project(self.alice, "Projet source", "Description")
        p.skip_weekends = skip
        p.save()
        a = Task.objects.create(project=p, title="A", start_date=MON, due_date=date(2026, 10, 14), priority=1)
        b = Task.objects.create(project=p, title="B", start_date=date(2026, 10, 15), due_date=date(2026, 10, 16), recurrence="weekly", is_milestone=True)
        b.dependencies.set([a])
        Task.objects.create(project=p, title="Sans date")
        Task.objects.create(project=p, title="Une seule date", due_date=date(2026, 10, 20))
        return p

    def test_save_then_reuse_reproduces_structure_with_a_shifted_start(self):
        src = self.build()
        saved = self.as_(self.alice).post(f"/api/projects/{src.pk}/save-template/", {"name": "Mon modèle"}, format="json")
        self.assertEqual((saved.status_code, saved.data["tasks"]), (201, 4))
        res = self.from_tpl(self.alice, template=str(saved.data["id"]), start_date="2027-01-04", name="Copie")
        copy = Project.objects.get(pk=res.data["id"])
        a, b = copy.tasks.get(title="A"), copy.tasks.get(title="B")
        self.assertEqual((a.start_date, a.due_date), (date(2027, 1, 4), date(2027, 1, 6)))  # même durée de 3 jours
        self.assertEqual((b.start_date, b.due_date), (date(2027, 1, 7), date(2027, 1, 8)))  # +3 jours : même décalage
        self.assertEqual([d.title for d in b.dependencies.all()], ["A"])
        self.assertEqual((a.priority, b.is_milestone, b.recurrence), (1, True, "weekly"))
        self.assertIsNone(copy.tasks.get(title="Sans date").start_date)
        single = copy.tasks.get(title="Une seule date")
        self.assertEqual((single.start_date, single.due_date), (date(2027, 1, 12), date(2027, 1, 12)))  # 20 oct. − 12 oct. = 8 jours après le début (4 jan. + 8)

    def test_working_day_projects_save_working_day_offsets(self):
        src = self.build(skip=True)
        saved = self.as_(self.alice).post(f"/api/projects/{src.pk}/save-template/", {"name": "Ouvrés"}, format="json").data
        tpl = ProjectTemplate.objects.get(pk=saved["id"])
        self.assertTrue(tpl.skip_weekends)
        offsets = {t["title"]: t["offset"] for t in tpl.tasks}
        self.assertEqual((offsets["A"], offsets["B"]), (0, 3))  # lun-mer puis jeu : 3 jours ouvrés d'écart
        res = self.from_tpl(self.alice, template=str(saved["id"]), start_date="2026-10-19")
        self.assertTrue(Project.objects.get(pk=res.data["id"]).skip_weekends)

    def test_only_the_owner_saves_and_the_name_is_required(self):
        src = self.build()
        from .models import Membership
        Membership.objects.create(project=src, user=self.bob, role="member")
        self.assertEqual(self.as_(self.bob).post(f"/api/projects/{src.pk}/save-template/", {"name": "x"}, format="json").status_code, 403)
        self.assertEqual(self.as_(self.alice).post(f"/api/projects/{src.pk}/save-template/", {"name": "  "}, format="json").status_code, 400)
        empty = create_project(self.alice, "Vide")
        self.assertEqual(self.client.post(f"/api/projects/{empty.pk}/save-template/", {"name": "x"}, format="json").status_code, 400)
        stranger = User.objects.create_user("eve", password="pw-test-123")
        self.assertEqual(self.as_(stranger).post(f"/api/projects/{src.pk}/save-template/", {"name": "x"}, format="json").status_code, 404)

    def test_templates_are_private(self):
        src = self.build()
        saved = self.as_(self.alice).post(f"/api/projects/{src.pk}/save-template/", {"name": "Privé"}, format="json").data
        self.assertEqual(self.from_tpl(self.bob, template=str(saved["id"])).status_code, 400)  # même erreur qu'un modèle inexistant
        self.assertEqual(self.as_(self.bob).delete(f"/api/templates/{saved['id']}/").status_code, 404)
        self.assertEqual(self.as_(self.alice).delete(f"/api/templates/{saved['id']}/").status_code, 204)
        self.assertEqual(ProjectTemplate.objects.count(), 0)

    def test_a_user_keeps_at_most_twenty_templates(self):
        src = self.build()
        for i in range(templates.MAX_TEMPLATES):
            ProjectTemplate.objects.create(owner=self.alice, name=f"m{i}", tasks=[])
        res = self.as_(self.alice).post(f"/api/projects/{src.pk}/save-template/", {"name": "de trop"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_deleting_the_owner_deletes_their_templates(self):
        ProjectTemplate.objects.create(owner=self.bob, name="x", tasks=[])
        self.bob.delete()
        self.assertEqual(ProjectTemplate.objects.count(), 0)

    def test_a_corrupted_template_does_not_crash(self):
        tpl = ProjectTemplate.objects.create(owner=self.alice, name="Cassé", tasks=[{"ref": "a", "title": "T", "offset": 0, "duration": 0, "depends_on": ["zzz"]}])
        res = self.from_tpl(self.alice, template=str(tpl.pk), start_date="2026-10-12")
        self.assertEqual(res.status_code, 201)  # durée 0 ramenée à 1 jour, dépendance inconnue ignorée
        self.assertEqual(Project.objects.get(pk=res.data["id"]).tasks.get().due_date, date(2026, 10, 12))
