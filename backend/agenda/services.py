"""Règles du calendrier : fuseaux horaires et droits sur les événements."""
import copy
from datetime import date, datetime, time, timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import Profile
from accounts.timezones import zone
from projects.models import Membership, Project
from projects.services import get_role
from tasks.models import Task

from .models import Event, EventSkip, Invitation

User = get_user_model()

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
    """Mes événements, ceux de mes projets, et ceux auxquels on m'a invité."""
    return Event.objects.filter(Q(project__membership__user=user) | Q(project__isnull=True, creator=user)
                                | Q(invitations__user=user)).distinct()


def can_edit(user, event):
    return _can_write(user, event)


def _check(data):
    if data["ends_at"] <= data["starts_at"]:
        raise ValidationError("La fin doit suivre le début.")
    if data["ends_at"] - data["starts_at"] > timedelta(days=MAX_EVENT_DAYS):
        raise ValidationError(f"Un événement dure {MAX_EVENT_DAYS} jours au plus.")
    if data.get("recurrence"):
        if data["ends_at"] - data["starts_at"] >= timedelta(days=1):
            raise ValidationError("Un événement récurrent dure moins d'un jour.")
        until = data.get("recurrence_until")
        if until and until < data["starts_at"].date():
            raise ValidationError("La fin de la récurrence précède le premier événement.")


# ------------------------------------------------------------------ invités
def contacts(user):
    """Personnes qui partagent au moins un de mes projets (les seules que je peux inviter à un événement personnel)."""
    ids = Membership.objects.filter(project__membership__user=user).exclude(user=user).values_list("user", flat=True)
    return User.objects.filter(pk__in=set(ids), is_active=True)


def set_invitees(user, event, user_ids):
    """Aligne les invités sur `user_ids` : ajoute (notifiés par l'invitation), retire les absents. Les invités d'un
    événement de projet sont des membres du projet ; ceux d'un événement personnel, des collègues."""
    ids = {int(i) for i in user_ids} - {user.pk}
    allowed = (User.objects.filter(membership__project=event.project, is_active=True) if event.project_id else contacts(user)).filter(pk__in=ids)
    if {u.pk for u in allowed} != ids:
        raise ValidationError("On ne peut inviter que des membres du projet (ou, pour un événement personnel, des collègues).")
    event.invitations.exclude(user_id__in=ids).delete()
    for u in allowed:
        Invitation.objects.get_or_create(event=event, user=u)


def rsvp(user, event, status):
    if status not in (Invitation.Status.ACCEPTED, Invitation.Status.DECLINED):
        raise ValidationError("Réponse attendue : accepted ou declined.")
    inv = Invitation.objects.filter(event=event, user=user).first()
    if inv is None:
        raise PermissionDenied("Vous n'êtes pas invité à cet événement.")
    inv.status, inv.seen_at = status, inv.seen_at or timezone.now()
    inv.save(update_fields=["status", "seen_at"])
    return inv


def my_status(user, event):
    """organizer | invited | accepted | declined | None (membre du projet non invité)."""
    if event.creator_id == user.pk:
        return "organizer"
    inv = next((i for i in event.invitations.all() if i.user_id == user.pk), None)
    return inv.status if inv else None


@transaction.atomic
def create_event(user, attendees=None, **data):
    _require_can_write(user, data.get("project"))
    _check(data)
    event = Event.objects.create(creator=user, **data)
    if attendees:
        set_invitees(user, event, attendees)
    return event


@transaction.atomic
def update_event(user, event, attendees=None, **data):
    if not _can_write(user, event):
        raise PermissionDenied("Vous ne pouvez pas modifier cet événement.")
    if "project" in data:
        _require_can_write(user, data["project"])
    merged = {"starts_at": event.starts_at, "ends_at": event.ends_at, "recurrence": event.recurrence,
              "recurrence_until": event.recurrence_until, **data}
    _check(merged)
    for key, value in data.items():
        setattr(event, key, value)
    event.save()
    if attendees is not None:
        set_invitees(user, event, attendees)
    return event


def delete_event(user, event):
    if not _can_write(user, event):
        raise PermissionDenied("Vous ne pouvez pas supprimer cet événement.")
    event.delete()


# ------------------------------------------------------------------ récurrence
HORIZON = timedelta(days=366 * 3)


def _add_months(day, n):
    m = day.month - 1 + n
    return day.year + m // 12, m % 12 + 1


def occurrences(event, start, end):
    """[(début, fin, jour local)] des occurrences de `event` qui touchent [start, end[ (instants UTC).
    Une récurrence garde la même heure *murale* dans le fuseau de l'événement (donc suit l'heure d'été)."""
    if not event.recurrence:
        return [(event.starts_at, event.ends_at, None)] if event.starts_at < end and event.ends_at > start else []
    tz = zone(event.timezone or "Europe/Paris")
    base = event.starts_at.astimezone(tz)
    length = event.ends_at - event.starts_at
    first = base.date()
    last = min(event.recurrence_until or first + HORIZON, first + HORIZON)
    lo = max(first, (start.astimezone(tz) - length).date() - timedelta(days=1))
    hi = min(last, end.astimezone(tz).date())
    skipped = {s.day for s in event.skips.all()}
    days = []
    if event.recurrence in ("daily", "weekdays"):
        d = lo
        while d <= hi:
            if event.recurrence == "daily" or d.weekday() < 5:
                days.append(d)
            d += timedelta(days=1)
    elif event.recurrence == "weekly":
        d = first + timedelta(days=-(-(lo - first).days // 7) * 7) if lo > first else first
        while d <= hi:
            days.append(d)
            d += timedelta(days=7)
    elif event.recurrence == "monthly":
        n = 0
        while True:
            y, m = _add_months(first, n)
            n += 1
            if date(y, m, 1) > hi:
                break
            try:
                d = date(y, m, first.day)  # le 31 saute les mois de 30 jours : jamais décalé en silence
            except ValueError:
                continue
            if lo <= d <= hi:
                days.append(d)
    out = []
    for d in days:
        if d in skipped or d > last:
            continue
        s = datetime.combine(d, base.time(), tzinfo=tz)
        if s < end and s + length > start:
            out.append((s, s + length, d))
    return out


@transaction.atomic
def skip_occurrence(user, event, day):
    """Supprime UNE occurrence d'une série (la série continue). `day` = jour local de l'occurrence."""
    if not _can_write(user, event):
        raise PermissionDenied("Vous ne pouvez pas modifier cet événement.")
    if not event.recurrence:
        raise ValidationError("Cet événement n'est pas récurrent : supprimez-le.")
    try:
        day = date.fromisoformat(str(day))
    except ValueError:
        raise ValidationError("Jour invalide.")
    if EventSkip.objects.filter(event=event, day=day).exists():
        return  # déjà supprimée : idempotent
    probe = datetime.combine(day, time.min, tzinfo=zone(event.timezone or "Europe/Paris"))
    if not [o for o in occurrences(event, probe, probe + timedelta(days=1)) if o[2] == day]:
        raise ValidationError("Il n'y a pas d'occurrence ce jour-là.")
    EventSkip.objects.get_or_create(event=event, day=day)


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
    events = visible_events(user).filter(Q(starts_at__lt=end, ends_at__gt=start) | (~Q(recurrence="") & Q(starts_at__lt=end)))
    tasks = Task.objects.filter(project__membership__user=user).filter(
        Q(due_date__range=(first, last)) | Q(start_date__range=(first, last))
        | Q(start_date__lte=first, due_date__gte=last)).select_related("project", "assignee")
    if project is not None:
        events, tasks = events.filter(project=project), tasks.filter(project=project)
    if mine:
        tasks = tasks.filter(assignee=user)
    shown = []
    for event in events.select_related("project", "creator").prefetch_related("invitations__user", "skips"):
        for occ_start, occ_end, day in occurrences(event, start, end):
            if day is None:
                shown.append(event)
                continue
            clone = copy.copy(event)  # une occurrence = l'événement avec ses horaires du jour ; la série garde les siens
            clone.series_starts_at, clone.series_ends_at, clone.occurrence_day = event.starts_at, event.ends_at, day
            clone.starts_at, clone.ends_at = occ_start, occ_end
            shown.append(clone)
    shown.sort(key=lambda e: (e.starts_at, e.pk))
    return shown, list(tasks.distinct())


def member_project(user, pk):
    """Projet dont `user` est membre (404 côté vue sinon)."""
    return Project.objects.filter(pk=pk, membership__user=user).first()
