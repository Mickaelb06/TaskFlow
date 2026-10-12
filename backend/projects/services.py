from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Membership, Project

User = get_user_model()


@transaction.atomic
def create_project(owner, name, description="", deadline=None):
    """Règle métier : le créateur devient automatiquement propriétaire."""
    project = Project.objects.create(owner=owner, name=name, description=description, deadline=deadline)
    Membership.objects.create(project=project, user=owner, role=Membership.Role.OWNER)
    return project


def get_role(user, project):
    m = Membership.objects.filter(project=project, user=user).first()
    return m.role if m else None


def _require_owner(actor, project):
    if get_role(actor, project) != Membership.Role.OWNER:
        raise PermissionDenied("Réservé au propriétaire du projet.")


def add_member(actor, project, identifier, role):
    _require_owner(actor, project)
    if role == Membership.Role.OWNER:
        raise ValidationError("Un projet n'a qu'un seul propriétaire.")
    user = User.objects.filter(Q(username=identifier) | Q(email__iexact=identifier)).first()
    if user is None:
        raise ValidationError("Utilisateur introuvable.")
    membership, created = Membership.objects.get_or_create(project=project, user=user, defaults={"role": role})
    if not created:
        raise ValidationError("Cet utilisateur est déjà membre du projet.")
    return membership


def change_role(actor, membership, role):
    _require_owner(actor, membership.project)
    if membership.role == Membership.Role.OWNER or role == Membership.Role.OWNER:
        raise ValidationError("Le rôle de propriétaire ne peut pas être modifié.")
    membership.role = role
    membership.save(update_fields=["role"])
    return membership


def remove_member(actor, membership):
    """Le propriétaire retire n'importe quel membre ; un membre peut quitter le projet."""
    is_self = membership.user_id == actor.id
    if not is_self:
        _require_owner(actor, membership.project)
    if membership.role == Membership.Role.OWNER:
        raise ValidationError("Le propriétaire ne peut pas quitter son projet.")
    # Les tâches assignées au membre retiré redeviennent non assignées
    membership.user.assigned_tasks.filter(project=membership.project).update(assignee=None)
    membership.delete()


@transaction.atomic
def transfer_ownership(project, new_owner):
    """Un projet a toujours exactement un propriétaire : l'ancien reste membre, le nouveau devient propriétaire."""
    old = project.owner
    Membership.objects.update_or_create(project=project, user=new_owner, defaults={"role": Membership.Role.OWNER})
    if old.pk != new_owner.pk:
        Membership.objects.filter(project=project, user=old).update(role=Membership.Role.MEMBER)
    project.owner = new_owner
    project.save(update_fields=["owner"])
    return project
