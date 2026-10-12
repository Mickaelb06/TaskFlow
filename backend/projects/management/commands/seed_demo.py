from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from projects.models import Membership
from projects.services import create_project
from agenda.models import Event
from tasks.models import Comment, Task
from zoneinfo import ZoneInfo

User = get_user_model()


class Command(BaseCommand):
    help = "Crée des données de démonstration (comptes demo / lea / sam, un projet solo, un projet d'équipe avec historique)."

    def handle(self, *args, **options):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@example.com", "admin-taskflow-2026")
            self.stdout.write(self.style.SUCCESS("Compte administrateur créé : admin / admin-taskflow-2026 (à changer en production)"))
        if User.objects.filter(username="demo").exists():
            self.seed_chat()
            self.seed_events()  # idempotent : ajoute l'agenda aux bases créées avant le calendrier
            self.stdout.write("Données de démonstration déjà présentes.")
            return
        demo = User.objects.create_user("demo", "demo@example.com", "demo-taskflow-2026", is_staff=True)  # admin ET propriétaire de projets : voit toutes les vues
        lea = User.objects.create_user("lea", "lea@example.com", "demo-taskflow-2026")
        sam = User.objects.create_user("sam", "sam@example.com", "demo-taskflow-2026")
        today = date.today()
        d = lambda n: today + timedelta(days=n)
        at = lambda n: timezone.make_aware(datetime.combine(d(n), time(10, 0)))

        def make(project, title, a=None, b=None, prio=2, status="todo", who=None, deps=(), milestone=False,
                 created=-14, done=None):
            """`created` / `done` : décalages en jours (passé) pour que les courbes aient un historique."""
            t = Task.objects.create(project=project, title=title, priority=prio, status="done" if done is not None else status,
                                    start_date=d(a) if a is not None else None, due_date=d(b) if b is not None else None,
                                    assignee=who, is_milestone=milestone)
            t.dependencies.set(deps)
            Task.objects.filter(pk=t.pk).update(created_at=at(created), completed_at=at(done) if done is not None else None)
            return t

        # --- projet solo
        perso = create_project(demo, "Perso", "Projet solo", d(20))
        make(perso, "Renouveler l'assurance", 1, 2, 2, who=demo, created=-6)
        make(perso, "Préparer la soutenance VAE", 3, 12, 1, "doing", demo, created=-10)
        make(perso, "Ranger le bureau", -3, -1, 3, who=demo, created=-8)
        make(perso, "Réserver le train", who=demo, created=-2)
        make(perso, "Prendre rendez-vous médecin", -9, -7, 2, who=demo, created=-12, done=-7)
        make(perso, "Envoyer le dossier VAE", -6, -4, 1, who=demo, created=-12, done=-4)
        make(perso, "Relire le livret", -3, -2, 2, who=demo, created=-9, done=-2)

        # --- projet d'équipe, planifié avec dépendances et historique
        site = create_project(demo, "Site web de l'association", "Refonte du site, en équipe", d(16))
        Membership.objects.create(project=site, user=lea, role="member")
        Membership.objects.create(project=site, user=sam, role="viewer")
        audit = make(site, "Audit du site actuel", -24, -21, 2, who=lea, created=-26, done=-20)
        cadrage = make(site, "Cadrage et besoins", -20, -14, 1, who=demo, deps=[audit], created=-25, done=-13)
        hebergeur = make(site, "Choix de l'hébergeur", -14, -11, 2, who=demo, created=-22, done=-10)
        charte = make(site, "Charte graphique", -13, -8, 2, who=lea, deps=[cadrage], created=-20, done=-7)
        maquettes = make(site, "Maquettes des pages", -6, 1, 1, "doing", lea, [charte], created=-14)
        legal = make(site, "Mentions légales et RGPD", -6, -2, 2, "todo", lea, [cadrage], created=-14)  # en retard
        contenus = make(site, "Collecte des contenus et photos", -3, 5, 3, "doing", None, [cadrage], created=-12)
        integration = make(site, "Intégration des pages", 2, 9, 1, "todo", lea, [maquettes, legal, hebergeur], created=-10)
        recette = make(site, "Recette avec l'équipe", 10, 12, 1, "todo", demo, [integration, contenus], created=-8)
        make(site, "Mise en ligne", 13, 13, 1, "todo", demo, [recette], milestone=True, created=-8)
        Comment.objects.create(task=maquettes, author=lea, content="Première version prête, je la partage demain.")
        Comment.objects.create(task=maquettes, author=demo, content="Parfait, merci !")
        self.seed_events()
        self.seed_chat()
        self.stdout.write(self.style.SUCCESS(
            "Comptes créés : demo / lea (membre) / sam (lecteur) — mot de passe : demo-taskflow-2026"))

    def seed_events(self):
        """Quelques rendez-vous répartis sur la semaine, dont un saisi dans un autre fuseau."""
        from projects.models import Project

        demo = User.objects.filter(username="demo").first()
        site = Project.objects.filter(name="Site web de l'association").first()
        paris, today = ZoneInfo("Europe/Paris"), date.today()
        monday = today - timedelta(days=today.weekday())
        # idempotent : on n'ajoute l'agenda que s'il n'y a encore rien depuis le début de la semaine en cours
        if demo is None or Event.objects.filter(starts_at__gte=datetime.combine(monday, time.min, tzinfo=paris)).exists():
            return

        def add(day, h, mi, minutes, title, project=None, tz="Europe/Paris", description=""):
            start = datetime.combine(monday + timedelta(days=day), time(h, mi), tzinfo=ZoneInfo(tz))
            Event.objects.create(project=project, creator=demo, title=title, description=description, timezone=tz,
                                 starts_at=start, ends_at=start + timedelta(minutes=minutes))

        for day in range(5):
            add(day, 9, 30, 15, "Point quotidien", site)
        add(1, 14, 0, 90, "Revue des maquettes", site, description="Valider la page d'accueil avant intégration.")
        add(2, 11, 0, 60, "Appel avec le prestataire (Montréal)", site, tz="America/Montreal", description="11 h à Montréal = 17 h en France.")
        add(3, 14, 30, 60, "Revue des maquettes — suite", site)
        add(3, 18, 30, 90, "Sport")
        add(4, 16, 0, 120, "Atelier d'écriture du contenu", site)
        add(0, 12, 30, 90, "Déjeuner")
        self.stdout.write(self.style.SUCCESS("Agenda de démonstration créé."))

    def seed_chat(self):
        """Un fil d'équipe avec mentions, un bloc-notes (projet solo) et une conversation directe."""
        from chat import services as chat
        from chat.models import Message
        from projects.models import Project

        if Message.objects.exists():
            return
        users = {u.username: u for u in User.objects.filter(username__in=["demo", "lea", "sam"])}
        site = Project.objects.filter(name="Site web de l'association").first()
        perso = Project.objects.filter(name="Perso").first()
        if len(users) < 3 or site is None or perso is None:
            return
        demo, lea = users["demo"], users["lea"]
        team = chat.project_conversation(demo, site)
        chat.post_message(lea, team, "Première version des maquettes prête, je la partage demain.")
        chat.post_message(demo, team, "Parfait @lea, merci ! @tous revue des maquettes jeudi à 14 h30.")
        chat.post_message(lea, team, "@demo j'ai besoin des photos de l'association pour l'intégration.")
        notes = chat.project_conversation(demo, perso)
        chat.post_message(demo, notes, "Penser à relire le livret avant la soutenance.")
        chat.post_message(demo, notes, "Idée : préparer une démo de 10 minutes du calendrier et des fuseaux.")
        direct = chat.direct_with(lea, demo)
        chat.post_message(lea, direct, "Tu as 5 minutes pour regarder la page d'accueil ?")
        self.stdout.write(self.style.SUCCESS("Messages de démonstration créés."))
