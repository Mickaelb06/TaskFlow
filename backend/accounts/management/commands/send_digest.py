from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.emails import _send, build_digest

User = get_user_model()


class Command(BaseCommand):
    help = ("Envoie le résumé du matin (agenda, tâches du jour et en retard, non lus) aux utilisateurs qui l'ont activé. "
            "À planifier chaque matin, ex. cron : « 0 7 * * 1-5  python manage.py send_digest ».")

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="affiche les résumés sans rien envoyer")

    def handle(self, *args, dry_run=False, **options):
        sent = 0
        for user in User.objects.filter(is_active=True, profile__digest_email=True).exclude(email=""):
            body = build_digest(user)
            if body is None:
                continue
            if dry_run:
                self.stdout.write(f"--- {user.username} <{user.email}>\n{body}\n")
            elif _send(user, "Votre journée sur TaskFlow", body):
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} résumé(s) envoyé(s)."))
