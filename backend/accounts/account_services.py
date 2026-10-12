"""Compte de l'utilisateur lui-même : export de ses données et suppression (RGPD)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Profile
from .admin_services import log, owned_projects_info, _another_admin_remains


def export_data(user):
    """Toutes les données personnelles, lisibles par un humain (JSON)."""
    from agenda.models import Event
    from chat.models import Message
    from projects.models import Membership
    from tasks.models import Comment, Task

    profile = Profile.for_user(user)
    iso = lambda d: d.isoformat() if d else None
    return {
        "exported_at": timezone.now().isoformat(),
        "account": {
            "username": user.username, "email": user.email, "date_joined": iso(user.date_joined), "last_login": iso(user.last_login),
            "is_staff": user.is_staff, "timezone": profile.timezone, "secondary_timezone": profile.secondary_timezone,
        },
        "projects": [{"name": m.project.name, "role": m.role, "owner": m.project.owner_id == user.pk}
                     for m in Membership.objects.filter(user=user).select_related("project")],
        "tasks_assigned": [{"project": t.project.name, "title": t.title, "status": t.status, "start_date": iso(t.start_date), "due_date": iso(t.due_date)}
                           for t in Task.objects.filter(assignee=user).select_related("project")],
        "comments": [{"task": c.task.title, "content": c.content, "created_at": iso(c.created_at)}
                     for c in Comment.objects.filter(author=user).select_related("task")],
        "events": [{"title": e.title, "starts_at": iso(e.starts_at), "ends_at": iso(e.ends_at), "project": e.project.name if e.project else None}
                   for e in Event.objects.filter(creator=user).select_related("project")],
        "messages": [{"conversation": _title(m.conversation), "content": m.content, "created_at": iso(m.created_at)}
                     for m in Message.objects.filter(author=user).select_related("conversation__project", "conversation__user_a", "conversation__user_b")],
    }


def _title(conv):
    if conv.kind == "project":
        return conv.project.name
    return "Direct : " + " / ".join([conv.user_a.username, conv.user_b.username])


@transaction.atomic
def delete_account(user, password):
    """Supprime le compte de `user`. Exige le mot de passe. Refus si on est le dernier administrateur actif ou si un
    projet partagé dépend encore de nous (il faut d'abord transférer la propriété) ; les projets où l'on est seul
    sont supprimés avec le compte. Les messages et commentaires restent, signés « Utilisateur supprimé »."""
    if not user.check_password(password or ""):
        raise ValidationError({"password": "Mot de passe incorrect."})
    if user.is_staff and user.is_active and not _another_admin_remains(user):
        raise ValidationError("Vous êtes le dernier administrateur actif : désignez-en un autre avant de supprimer votre compte.")
    shared = [p["name"] for p in owned_projects_info(user) if p["other_members"] > 0]
    if shared:
        raise ValidationError("Transférez d'abord la propriété de ces projets partagés (Membres → Transférer) : " + ", ".join(shared) + ".")
    from agenda.models import Event

    for project in user.owned_projects.all():  # projets solo
        project.delete()
    Event.objects.filter(project__isnull=True, creator=user).delete()
    label = user.username
    log(user, "user.self_delete", label)
    user.delete()
