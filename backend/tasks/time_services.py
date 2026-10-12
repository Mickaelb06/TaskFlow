"""Suivi du temps : chrono (démarrer / arrêter) et saisie manuelle, par tâche."""
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import Profile
from accounts.timezones import zone
from projects.models import Membership

from .models import TimeEntry
from .services import WRITE_ROLES, _require_writer

MAX_MINUTES = 12 * 60  # un chrono oublié est plafonné : on ne facture pas la nuit


def _local_day(user, moment=None):
    return (moment or timezone.now()).astimezone(zone(Profile.for_user(user).timezone)).date()


def running(user):
    return TimeEntry.objects.filter(user=user, minutes__isnull=True).select_related("task__project").first()


def _finish(entry, now):
    seconds = (now - entry.started_at).total_seconds()
    entry.minutes = max(1, min(MAX_MINUTES, round(seconds / 60)))
    entry.save(update_fields=["minutes"])
    return entry


@transaction.atomic
def start(user, task):
    """Démarre le chrono sur `task` ; celui qui tournait ailleurs est arrêté (un seul chrono à la fois)."""
    _require_writer(user, task.project)
    now = timezone.now()
    current = running(user)
    if current:
        _finish(current, now)
    return TimeEntry.objects.create(task=task, user=user, started_at=now, day=_local_day(user, now))


@transaction.atomic
def stop(user):
    current = running(user)
    if current is None:
        raise ValidationError("Aucun chrono en cours.")
    return _finish(current, timezone.now())


def add_manual(user, task, minutes, day=None, note=""):
    _require_writer(user, task.project)
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise ValidationError("Durée en minutes attendue.")
    if not 1 <= minutes <= 1440:
        raise ValidationError("Entre 1 minute et 24 heures par saisie.")
    today = _local_day(user)
    day = day or today
    if day > today + timedelta(days=1):
        raise ValidationError("Impossible de saisir du temps dans le futur.")
    if day < today - timedelta(days=366):
        raise ValidationError("Saisie trop ancienne (un an au plus).")
    return TimeEntry.objects.create(task=task, user=user, day=day, minutes=minutes, note=note[:200])


def delete_entry(user, entry):
    """On supprime ses propres saisies ; le propriétaire du projet peut corriger celles des autres."""
    owner = Membership.objects.filter(project=entry.task.project, user=user, role=Membership.Role.OWNER).exists()
    if entry.user_id != user.pk and not owner:
        raise PermissionDenied("Vous ne pouvez supprimer que votre propre temps.")
    entry.delete()


def total(task):
    return TimeEntry.objects.filter(task=task, minutes__isnull=False).aggregate(t=Sum("minutes"))["t"] or 0


def report(project, first, last):
    """Temps passé entre deux jours : total, par membre, par tâche (10 premières), par jour."""
    qs = TimeEntry.objects.filter(task__project=project, minutes__isnull=False, day__range=(first, last)).select_related("user", "task")
    by_user, by_task, by_day = {}, {}, {}
    for e in qs:
        name = e.user.username if e.user else "Utilisateur supprimé"
        by_user[name] = by_user.get(name, 0) + e.minutes
        by_task[e.task_id] = (e.task.title, by_task.get(e.task_id, ("", 0))[1] + e.minutes)
        by_day[e.day] = by_day.get(e.day, 0) + e.minutes
    return {
        "from": first, "to": last, "total": sum(by_user.values()),
        "by_member": sorted(({"user": k, "minutes": v} for k, v in by_user.items()), key=lambda r: (-r["minutes"], r["user"])),
        "by_task": sorted(({"task": k, "title": t, "minutes": m} for k, (t, m) in by_task.items()), key=lambda r: (-r["minutes"], r["task"]))[:10],
        "by_day": [{"day": d, "minutes": by_day.get(d, 0)} for d in (first + timedelta(days=i) for i in range((last - first).days + 1))],
    }
