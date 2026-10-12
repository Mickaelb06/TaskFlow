from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

User = get_user_model()


class PromoteAdminTests(TestCase):
    def test_promeut_un_compte_existant(self):
        User.objects.create_user("alice", "a@x.fr", "pw-12345-xyz")
        call_command("promote_admin", "Alice", stdout=StringIO())
        u = User.objects.get(username="alice")
        self.assertTrue(u.is_staff and u.is_superuser and u.is_active)

    def test_compte_inconnu_ne_cree_rien(self):
        with self.assertRaises(CommandError):
            call_command("promote_admin", "fantome", stdout=StringIO())
        self.assertFalse(User.objects.filter(username="fantome").exists())
