from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Donne les droits d'administrateur (et de superutilisateur) à un compte existant : premier admin d'un site neuf."

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, username, **options):
        User = get_user_model()
        user = User.objects.filter(username__iexact=username).first()
        if user is None:
            raise CommandError(f"Aucun compte « {username} » : inscrivez-vous d'abord sur le site.")
        user.is_active = user.is_staff = user.is_superuser = True
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        self.stdout.write(f"{user.username} est maintenant administrateur.")
