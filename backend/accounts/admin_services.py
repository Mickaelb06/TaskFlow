"""Actions d'administration : règles de sécurité + journal d'audit.

Règles : on ne peut pas se désactiver / se supprimer / se retirer ses droits ; il reste toujours au moins un
administrateur actif ; seul un superutilisateur peut toucher à un superutilisateur ; un utilisateur qui possède
des projets ne peut être supprimé qu'après transfert (ou suppression de ses projets solo).
"""
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from projects.models import Project
from projects.services import transfer_ownership
from tasks.models import Comment, Task

from .models import AuditLog, SiteSettings

User = get_user_model()


class NeedsTransfer(Exception):
    """L'utilisateur possède des projets : il faut choisir un repreneur (ou supprimer les projets solo)."""

    def __init__(self, projects):
        self.projects = projects


def log(actor, action, target="", **details):
    AuditLog.objects.create(actor=actor, actor_name=actor.username, action=action, target=target, details=details)


def generate_password():
    return secrets.token_urlsafe(9)  # ~12 caractères, généré par le module `secrets`


def _check_password(password, user):
    try:
        validate_password(password, user)
    except DjangoValidationError as e:
        raise ValidationError({"password": e.messages})


def _guard(actor, target):
    if target.is_superuser and not actor.is_superuser:
        raise PermissionDenied("Seul un superutilisateur peut modifier un superutilisateur.")


def _another_admin_remains(excluding):
    return User.objects.filter(is_staff=True, is_active=True).exclude(pk=excluding.pk).exists()


def _label(user):
    return f"{user.username} ({user.email})" if user.email else user.username


# ------------------------------------------------------------ utilisateurs
@transaction.atomic
def create_user(actor, username, email, password=None, is_staff=False):
    if User.objects.filter(username__iexact=username).exists():
        raise ValidationError({"username": "Ce nom d'utilisateur existe déjà."})
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "Cet email est déjà utilisé."})
    generated = None
    if not password:
        password = generated = generate_password()
    else:
        _check_password(password, User(username=username, email=email))
    user = User.objects.create_user(username=username, email=email, password=password, is_staff=is_staff)
    log(actor, "user.create", _label(user), is_staff=is_staff, password_generated=bool(generated))
    return user, generated


@transaction.atomic
def update_user(actor, target, email=None, is_active=None, is_staff=None):
    _guard(actor, target)
    if email is not None and email.lower() != target.email.lower():
        if User.objects.filter(email__iexact=email).exclude(pk=target.pk).exists():
            raise ValidationError({"email": "Cet email est déjà utilisé."})
        log(actor, "user.update", _label(target), email=[target.email, email])
        target.email = email
    if is_active is not None and is_active != target.is_active:
        if not is_active:
            if target.pk == actor.pk:
                raise ValidationError("Vous ne pouvez pas désactiver votre propre compte.")
            if target.is_staff and not _another_admin_remains(target):
                raise ValidationError("Il doit rester au moins un administrateur actif.")
        target.is_active = is_active
        log(actor, "user.activate" if is_active else "user.deactivate", _label(target))
    if is_staff is not None and is_staff != target.is_staff:
        if not is_staff:
            if target.pk == actor.pk:
                raise ValidationError("Vous ne pouvez pas retirer vos propres droits d'administrateur.")
            if target.is_active and not _another_admin_remains(target):
                raise ValidationError("Il doit rester au moins un administrateur actif.")
        target.is_staff = is_staff
        log(actor, "user.promote" if is_staff else "user.demote", _label(target))
    target.save()
    return target


@transaction.atomic
def reset_password(actor, target, password=None):
    _guard(actor, target)
    generated = None
    if not password:
        password = generated = generate_password()
    else:
        _check_password(password, target)
    target.set_password(password)
    target.save(update_fields=["password"])
    log(actor, "user.password_reset", _label(target), password_generated=bool(generated))
    return generated


def owned_projects_info(user):
    return [{"id": p.pk, "name": p.name, "other_members": p.membership_set.exclude(user=user).count()}
            for p in user.owned_projects.all()]


@transaction.atomic
def delete_user(actor, target, transfer_to=None, delete_solo=False):
    _guard(actor, target)
    if target.pk == actor.pk:
        raise ValidationError("Vous ne pouvez pas supprimer votre propre compte.")
    if target.is_staff and target.is_active and not _another_admin_remains(target):
        raise ValidationError("Il doit rester au moins un administrateur actif.")

    owned = owned_projects_info(target)
    heir = None
    if transfer_to is not None:
        heir = User.objects.filter(pk=transfer_to, is_active=True).exclude(pk=target.pk).first()
        if heir is None:
            raise ValidationError({"transfer_to": "Le repreneur doit être un autre utilisateur actif."})
    must_transfer = [p for p in owned if not (delete_solo and p["other_members"] == 0)]
    if must_transfer and heir is None:
        raise NeedsTransfer(owned)

    transferred = deleted = 0
    for info in owned:
        project = Project.objects.get(pk=info["id"])
        if delete_solo and info["other_members"] == 0:
            project.delete()
            deleted += 1
        else:
            transfer_ownership(project, heir)
            transferred += 1
    label = _label(target)
    details = {"projects_transferred": transferred, "projects_deleted": deleted,
               "transferred_to": heir.username if heir else None}
    from agenda.models import Event  # import tardif : agenda dépend d'accounts

    Event.objects.filter(project__isnull=True, creator=target).delete()  # événements personnels
    target.delete()  # tâches → non assignées, commentaires → « utilisateur supprimé », adhésions supprimées
    log(actor, "user.delete", label, **details)


# ------------------------------------------------------------ projets
@transaction.atomic
def delete_project(actor, project):
    log(actor, "project.delete", project.name, owner=project.owner.username, tasks=project.tasks.count())
    project.delete()


@transaction.atomic
def transfer_project(actor, project, user_id):
    new_owner = User.objects.filter(pk=user_id, is_active=True).first()
    if new_owner is None:
        raise ValidationError({"user_id": "Utilisateur actif introuvable."})
    old = project.owner
    transfer_ownership(project, new_owner)
    log(actor, "project.transfer", project.name, **{"from": old.username, "to": new_owner.username})
    return project


# ------------------------------------------------------------ réglages
@transaction.atomic
def update_settings(actor, **changes):
    s = SiteSettings.get()
    diff = {}
    for key, value in changes.items():
        if value is not None and getattr(s, key) != value:
            diff[key] = [getattr(s, key), value]
            setattr(s, key, value)
    if diff:
        s.save()
        log(actor, "settings.update", "Réglages", **diff)
    return s


# ------------------------------------------------------------ statistiques
def stats(now=None):
    now = now or timezone.now()
    users = User.objects
    tasks = Task.objects
    weeks = []
    for i in range(7, -1, -1):
        end = now - timedelta(days=7 * i)
        weeks.append({"date": timezone.localtime(end).date(),
                      "count": users.filter(date_joined__gt=end - timedelta(days=7), date_joined__lte=end).count()})
    return {
        "users": {"total": users.count(), "active": users.filter(is_active=True).count(),
                  "inactive": users.filter(is_active=False).count(), "admins": users.filter(is_staff=True, is_active=True).count(),
                  "new_30_days": users.filter(date_joined__gte=now - timedelta(days=30)).count(),
                  "active_30_days": users.filter(last_login__gte=now - timedelta(days=30)).count()},
        "projects": Project.objects.count(),
        "tasks": {"total": tasks.count(), "done": tasks.filter(status="done").count(),
                  "open": tasks.exclude(status="done").count()},
        "comments": Comment.objects.count(),
        "signups_weekly": weeks,
        "recent_users": [{"id": u.pk, "username": u.username, "email": u.email, "date_joined": u.date_joined}
                         for u in users.order_by("-date_joined")[:5]],
    }


def user_queryset():
    return User.objects.annotate(
        project_count=Count("membership", distinct=True),
        owned_count=Count("owned_projects", distinct=True),
        open_tasks=Count("assigned_tasks", filter=~Q(assigned_tasks__status="done"), distinct=True),
    )
