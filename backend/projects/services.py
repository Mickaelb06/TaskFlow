import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import Http404
from django.utils import timezone

from .models import Membership, Project, ProjectInvite

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


def transfer_to_member(actor, project, user_id):
    """Le propriétaire cède le projet à un de ses membres (il devient simple membre)."""
    _require_owner(actor, project)
    target = Membership.objects.filter(project=project, user_id=user_id).select_related("user").first()
    if target is None:
        raise ValidationError("Le nouveau propriétaire doit déjà être membre du projet.")
    if target.user_id == actor.pk:
        raise ValidationError("Vous êtes déjà propriétaire.")
    return transfer_ownership(project, target.user)


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


# ---------- liens d'invitation ----------
INVITE_DAYS = (1, 7, 30)
INVITE_MAX_ACTIVE = 20


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _active_invites(project):
    return project.invites.filter(revoked=False, expires_at__gt=timezone.now(), uses__lt=F("max_uses"))


def create_invite(actor, project, role=Membership.Role.MEMBER, days=7, max_uses=10):
    """Crée un lien ; renvoie (invitation, jeton en clair). Le jeton n'est plus récupérable ensuite."""
    _require_owner(actor, project)
    if role not in (Membership.Role.MEMBER, Membership.Role.VIEWER):
        raise ValidationError("Un lien ne peut donner que le rôle membre ou lecteur.")
    if days not in INVITE_DAYS:
        raise ValidationError("Durée de validité inconnue.")
    if not 1 <= max_uses <= 100:
        raise ValidationError("Le nombre d'utilisations doit être compris entre 1 et 100.")
    if _active_invites(project).count() >= INVITE_MAX_ACTIVE:
        raise ValidationError("Trop de liens actifs : révoquez-en avant d'en créer un nouveau.")
    token = secrets.token_urlsafe(32)
    invite = ProjectInvite.objects.create(
        project=project, token_hash=_hash(token), role=role, created_by=actor, max_uses=max_uses,
        expires_at=timezone.now() + timedelta(days=days),
    )
    return invite, token


def list_invites(actor, project):
    _require_owner(actor, project)
    return _active_invites(project).order_by("-created_at", "-id")


def revoke_invite(actor, project, invite_id):
    _require_owner(actor, project)
    updated = project.invites.filter(pk=invite_id).update(revoked=True)
    if not updated:
        raise Http404


def find_invite(token):
    """Invitation encore valable, ou 404 : la réponse est la même pour un jeton inconnu, expiré, révoqué ou épuisé."""
    invite = (ProjectInvite.objects.select_related("project", "created_by")
              .filter(token_hash=_hash(token or ""), revoked=False, expires_at__gt=timezone.now(), uses__lt=F("max_uses")).first())
    if invite is None:
        raise Http404
    return invite


@transaction.atomic
def accept_invite(user, token):
    """Ajoute l'utilisateur au projet. Renvoie (projet, déjà_membre). Un membre existant n'est ni rétrogradé ni compté."""
    invite = find_invite(token)
    invite = ProjectInvite.objects.select_for_update().select_related("project").get(pk=invite.pk)
    if invite.uses >= invite.max_uses or invite.revoked or invite.expires_at <= timezone.now():
        raise Http404
    _, created = Membership.objects.get_or_create(project=invite.project, user=user, defaults={"role": invite.role})
    if created:
        invite.uses += 1
        invite.save(update_fields=["uses"])
    return invite.project, not created


# ---------- recherche de personnes à ajouter ----------
SEARCH_MIN, SEARCH_MAX = 1, 8


def search_candidates(actor, project, query):
    """Comptes dont le nom commence par `query` (un « @ » initial est ignoré), hors membres actuels.
    Réservé au propriétaire, 1 caractère minimum (la première lettre après « @ »), 8 résultats : pas un annuaire de tous les comptes."""
    _require_owner(actor, project)
    q = (query or "").strip().lstrip("@").strip()
    if len(q) < SEARCH_MIN:
        return []
    members = Membership.objects.filter(project=project).values("user")
    return list(User.objects.filter(username__istartswith=q, is_active=True).exclude(pk__in=members).order_by("username")[:SEARCH_MAX])
