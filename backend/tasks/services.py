import calendar
from datetime import date, timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from projects.models import Membership
from projects.services import get_role

from . import planning
from . import workdays as wd
from .models import Comment, Task

WRITE_ROLES = (Membership.Role.OWNER, Membership.Role.MEMBER)


def _require_writer(user, project):
    if get_role(user, project) not in WRITE_ROLES:
        raise PermissionDenied("Seuls les propriétaires et membres peuvent modifier le projet.")


def _enforce_dependencies(task):
    """Une tâche ne peut pas commencer avant la fin de ses prédécesseurs, et ses successeurs suivent."""
    for pred in task.dependencies.all():
        planning.cascade(pred)
    planning.cascade(task)


def _next_due(day, rule, workdays):
    """Date de l'occurrence suivante d'une tâche récurrente qui se terminait le `day`."""
    if rule == "daily":
        nxt = day + timedelta(days=1)
    elif rule == "weekdays":
        nxt = day + timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
    elif rule == "weekly":
        nxt = day + timedelta(days=7)
    else:  # monthly : même quantième, ramené à la fin du mois s'il n'existe pas (31 janvier → 28 février)
        year, month = day.year + day.month // 12, day.month % 12 + 1
        nxt = date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
    return wd.next_workday(nxt) if workdays else nxt


def _spawn_next(task):
    """Crée l'occurrence suivante d'une tâche récurrente qu'on vient de terminer (une seule fois par tâche : rouvrir puis
    terminer à nouveau ne duplique rien). Copie titre, description, priorité, responsable et jalon, pas les dépendances."""
    if not task.recurrence or Task.objects.filter(recurrence_of=task).exists():
        return None
    workdays = task.project.skip_weekends
    start, due = task.start_date, task.due_date
    new_start = new_due = None
    if due:
        new_due = _next_due(due, task.recurrence, workdays)
        if start:
            new_start = new_due - (due - start)  # même durée
    elif start:
        new_start = _next_due(start, task.recurrence, workdays)
    return Task.objects.create(
        project=task.project, title=task.title, description=task.description, priority=task.priority, assignee=task.assignee,
        is_milestone=task.is_milestone, recurrence=task.recurrence, recurrence_of=task, start_date=new_start, due_date=new_due)


@transaction.atomic
def create_task(user, project, **data):
    _require_writer(user, project)
    deps = data.pop("dependencies", [])
    if data.get("status") == "done":
        data["completed_at"] = timezone.now()
    task = Task.objects.create(project=project, **data)
    if task.status == "done":
        _spawn_next(task)
    if deps:
        task.dependencies.set(deps)
        _enforce_dependencies(task)
        task.refresh_from_db()
    return task


@transaction.atomic
def update_task(user, task, data):
    _require_writer(user, task.project)
    data = dict(data)
    deps = data.pop("dependencies", None)
    was_done = task.status == "done"
    if "status" in data:  # historique : sert aux courbes d'avancement et à la vélocité
        task.completed_at = (task.completed_at or timezone.now()) if data["status"] == "done" else None
    for field, value in data.items():
        setattr(task, field, value)
    task.save()
    if task.status == "done" and not was_done:
        _spawn_next(task)
    if deps is not None:
        task.dependencies.set(deps)
    if deps is not None or {"start_date", "due_date"} & data.keys():
        _enforce_dependencies(task)
        task.refresh_from_db()
    return task


def add_comment(user, task, content):
    _require_writer(user, task.project)
    return Comment.objects.create(task=task, author=user, content=content)


