from rest_framework.permissions import BasePermission


class IsAppAdmin(BasePermission):
    """Réservé aux comptes actifs marqués is_staff. Vérifié côté serveur : masquer un bouton ne suffit pas."""

    message = "Réservé aux administrateurs."

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and u.is_staff)
