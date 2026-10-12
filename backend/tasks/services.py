from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from projects.models import Membership
from projects.services import get_role

from . import planning
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


@transaction.atomic
def create_task(user, project, **data):
    _require_writer(user, project)
    deps = data.pop("dependencies", [])
    if data.get("status") == "done":
        data["completed_at"] = timezone.now()
    task = Task.objects.create(project=project, **data)
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
    if "status" in data:  # historique : sert aux courbes d'avancement et à la vélocité
        task.completed_at = (task.completed_at or timezone.now()) if data["status"] == "done" else None
    for field, value in data.items():
        setattr(task, field, value)
    task.save()
    if deps is not None:
        task.dependencies.set(deps)
    if deps is not None or {"start_date", "due_date"} & data.keys():
        _enforce_dependencies(task)
        task.refresh_from_db()
    return task


def add_comment(user, task, content):
    _require_writer(user, task.project)
    return Comment.objects.create(task=task, author=user, content=content)


