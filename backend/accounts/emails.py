"""E-mails de TaskFlow : mention, invitation, résumé du matin. Jamais bloquants : une panne du serveur de messagerie
ne doit pas empêcher d'envoyer un message ou de créer un événement (l'erreur est journalisée)."""
import logging
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction

from .models import Profile
from .timezones import zone

log = logging.getLogger(__name__)
MENTION_COOLDOWN = 600  # secondes : au plus un e-mail de mention par fil et par personne toutes les 10 minutes


def _send(user, subject, body):
    if not user.email or not user.is_active:
        return False
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return True
    except Exception:  # noqa: BLE001 — jamais bloquant
        log.exception("Envoi d'e-mail impossible pour %s", user.username)
        return False


def _wants(user):
    return Profile.for_user(user).notify_email


def notify_mentions(message, users):
    """E-mail aux personnes mentionnées (si elles l'acceptent), limité à un par fil et par 10 minutes."""
    conv = message.conversation
    title = conv.project.name if conv.project_id else "message direct"
    author = message.author.username if message.author else "Quelqu'un"
    link = f"{settings.SITE_URL}/"
    for user in users:
        key = f"mail-mention:{user.pk}:{conv.pk}"
        if not _wants(user) or cache.get(key):
            continue
        cache.set(key, 1, MENTION_COOLDOWN)
        excerpt = " ".join(message.content.split())[:300]
        transaction.on_commit(lambda u=user: _send(
            u, f"{author} vous a mentionné dans « {title} »",
            f"Bonjour {u.username},\n\n{author} vous a mentionné dans « {title} » :\n\n  « {excerpt} »\n\nOuvrez TaskFlow pour répondre : {link}\n\n"
            "Vous recevez cet e-mail parce que les notifications par e-mail sont activées (Mon compte → Notifications)."))


def notify_invitation(invitation):
    user, event = invitation.user, invitation.event
    if not _wants(user):
        return
    tz = zone(Profile.for_user(user).timezone)
    when = event.starts_at.astimezone(tz).strftime("%d/%m/%Y à %H:%M")
    who = event.creator.username if event.creator else "Quelqu'un"
    transaction.on_commit(lambda: _send(
        user, f"Invitation : {event.title}",
        f"Bonjour {user.username},\n\n{who} vous invite à « {event.title} » le {when} ({tz.key}).\n\n"
        f"Répondez depuis TaskFlow : {settings.SITE_URL}/\n"))


def build_digest(user, now=None):
    """Texte du résumé du matin, ou None s'il n'y a rien à dire : tâches du jour et en retard, événements du jour."""
    from agenda.models import Event
    from agenda.services import occurrences, visible_events
    from chat.services import summary
    from tasks.models import Task

    tz = zone(Profile.for_user(user).timezone)
    now = now or datetime.now(tz)
    today = now.astimezone(tz).date()
    start = datetime.combine(today, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    tasks = Task.objects.filter(assignee=user).exclude(status="done").select_related("project")
    late = [t for t in tasks if t.due_date and t.due_date < today]
    due = [t for t in tasks if t.due_date == today]
    events = []
    for e in visible_events(user).filter(starts_at__lt=end).prefetch_related("skips", "invitations"):
        if any(i.user_id == user.pk and i.status == "declined" for i in e.invitations.all()):
            continue
        events += [(o[0], e) for o in occurrences(e, start, end)]
    events.sort(key=lambda x: x[0])
    unread = summary(user)
    if not (late or due or events or unread["unread_notifications"]):
        return None
    lines = [f"Bonjour {user.username}, voici votre journée du {today.strftime('%d/%m/%Y')} :", ""]
    if events:
        lines.append("Agenda")
        lines += [f"  {s.astimezone(tz).strftime('%H:%M')}  {e.title}" for s, e in events]
        lines.append("")
    if due:
        lines.append("À terminer aujourd'hui")
        lines += [f"  • {t.title} ({t.project.name})" for t in due]
        lines.append("")
    if late:
        lines.append("En retard")
        lines += [f"  • {t.title} ({t.project.name}) — échéance {t.due_date.strftime('%d/%m')}" for t in late]
        lines.append("")
    if unread["unread_notifications"] or unread["unread_messages"]:
        lines.append(f"Non lus : {unread['unread_messages']} message(s), {unread['unread_notifications']} notification(s).")
        lines.append("")
    lines.append(f"{settings.SITE_URL}/")
    return "\n".join(lines)
