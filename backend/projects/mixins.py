from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS

from .models import Membership, Project
from .services import get_role


class ProjectScopedMixin:
    """Charge le projet de l'URL (404 si l'utilisateur n'en est pas membre)
    et refuse les écritures aux rôles non autorisés."""

    write_roles = (Membership.Role.OWNER, Membership.Role.MEMBER)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # authentification d'abord
        self.project = get_object_or_404(Project, pk=kwargs["project_pk"], membership__user=request.user)
        self.role = get_role(request.user, self.project)
        if request.method not in SAFE_METHODS and self.role not in self.write_roles:
            raise PermissionDenied("Droits insuffisants pour cette action.")
