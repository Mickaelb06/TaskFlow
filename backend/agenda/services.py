"""Règles du calendrier : fuseaux horaires et droits sur les événements."""
from datetime import date, datetime, time, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from accounts.models import Profile
from accounts.timezones import zone
from projects.models import Membership, Project
from projects.services import get_role
from tasks.models import Task

from .models import Event

WRITE_ROLES = (Membership.Role.OWNER, Membership.Role.MEMBER)
MAX_RANGE_DAYS = 62  # une vue « mois » complète tient dans 6 semaines
MAX_EVENT_DAYS = 31


# ------------------------------------------------------------------ fuseaux
def user_zone(user):
    return zone(Profile.for_user(user).timezone)


def to_aware(value, tz):
    """Interprète une date-heure : avec décalage (« …+09:00 ») elle est prise telle quelle ; sans décalage,
    c'est l'heure *murale* du fuseau `tz`. Une heure inexistante (saut de printemps) avance d'une heure,
    une heure répétée (retour d'automne) prend sa première occurrence."""
    dt = parse_datetime(value) if isinstance(value, str) else value
    if dt is None:
        raise ValidationError("Date-heure invalide.")
    if dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=tz, fold=0)


def day_bounds(first, last, tz):
    """Instants UTC couvrant les jours calendaires [first, last] vus depuis `tz` (bornes [début, fin[)."""
    start = datetime.combine(first, time.min, tzinfo=tz)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


# ------------------------------------------------------------------ droits
def _require_can_write(user, project):
    if project is None:
        return
    if get_role(user, project) not in WRITE_ROLES:
        raise PermissionDenied("Seuls les propriétaires et membres peuvent modifier les événements du projet.")


def _can_write(user, event):
    if event.project_id is None:
        return event.creator_id == user.pk
    return get_role(user, event.project) in WRITE_ROLES


def visible_events(user):
    return Event.objects.filter(Q(project__membership__user=user) | Q(project__isnull=True, creator=user)).distinct()


def can_edit(user, event):
    return _can_write(user, event)


def _check(data):
    if data["ends_at"] <= data["starts_at"]:
        raise ValidationError("La fin doit suivre le début.")
    if data["ends_at"] - data["starts_at"] > timedelta(days=MAX_EVENT_DAYS):
        raise ValidationError(f"Un événement dure {MAX_EVENT_DAYS} jours au plus.")


def create_event(user, **data):
    _require_can_write(user, data.get("project"))
    _check(data)
    return Event.objects.create(creator=user, **data)


def update_event(user, event, **data):
    if not _can_write(user, event):
        raise PermissionDenied("Vous ne pouvez pas modifier cet événement.")
    if "project" in data:
        _require_can_write(user, data["project"])
    merged = {"starts_at": event.starts_at, "ends_at": event.ends_at, **data}
    _check(merged)
    for key, value in data.items():
        setattr(event, key, value)
    event.save()
    return event


def delete_event(user, event):
    if not _can_write(user, event):
        raise PermissionDenied("Vous ne pouvez pas supprimer cet événement.")
    event.delete()


# ------------------------------------------------------------------ vue calendrier
def parse_range(first, last):
    try:
        first, last = date.fromisoformat(first), date.fromisoformat(last)
    except (TypeError, ValueError):
        raise ValidationError("Paramètres « from » et « to » attendus au format AAAA-MM-JJ.")
    if last < first:
        raise ValidationError("« to » doit suivre « from ».")
    if (last - first).days > MAX_RANGE_DAYS:
        raise ValidationError(f"Période limitée à {MAX_RANGE_DAYS} jours.")
    return first, last


def calendar(user, first, last, project=None, mine=False):
    """Événements (avec heure) et tâches (à la journée) visibles par `user` sur [first, last]."""
    tz = user_zone(user)
    start, end = day_bounds(first, last, tz)
    events = visible_events(user).filter(starts_at__lt=end, ends_at__gt=start)
    tasks = Task.objects.filter(project__membership__user=user).filter(
        Q(due_date__range=(first, last)) | Q(start_date__range=(first, last))
        | Q(start_date__lte=first, due_date__gte=last)).select_related("project", "assignee")
    if project is not None:
        events, tasks = events.filter(project=project), tasks.filter(project=project)
    if mine:
        tasks = tasks.filter(assignee=user)
    return list(events.select_related("project", "creator")), list(tasks.distinct())


def member_project(user, pk):
    """Projet dont `user` est membre (404 côté vue sinon)."""
    return Project.objects.filter(pk=pk, membership__user=user).first()
