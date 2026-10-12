"""Règles de la messagerie : qui lit, qui écrit, qui est mentionné, ce qui reste non lu."""
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from projects.models import Membership, Project

from .models import Conversation, Message, Notification, ReadMark

User = get_user_model()
MAX_LENGTH = 2000
PAGE = 50
EVERYONE = ("tous", "all")
# « @nom » : pas collé à un mot (évite les emails), accepte nom.prenom, nom-x ; la ponctuation finale est exclue
MENTION = re.compile(r"(?<![\w@])@(\w+(?:[.\-+]\w+)*)")


# ------------------------------------------------------------------ accès
def participants(conv):
    if conv.kind == Conversation.Kind.DIRECT:
        return [conv.user_a, conv.user_b]
    return [m.user for m in Membership.objects.filter(project=conv.project).select_related("user")]


def _role(user, conv):
    return Membership.objects.filter(project=conv.project, user=user).values_list("role", flat=True).first()


def can_read(user, conv):
    if conv.kind == Conversation.Kind.DIRECT:
        return user.pk in (conv.user_a_id, conv.user_b_id)
    return _role(user, conv) is not None


def can_write(user, conv):
    if conv.kind == Conversation.Kind.DIRECT:
        return can_read(user, conv)
    return _role(user, conv) in (Membership.Role.OWNER, Membership.Role.MEMBER)  # un lecteur lit seulement


def is_solo(conv):
    return conv.kind == Conversation.Kind.PROJECT and Membership.objects.filter(project=conv.project).count() == 1


def conversation_for(user, pk):
    """Conversation lisible par `user` ; None sinon (la vue répond 404 : on ne révèle pas son existence)."""
    conv = Conversation.objects.filter(pk=pk).select_related("project", "user_a", "user_b").first()
    return conv if conv and can_read(user, conv) else None


def project_conversation(user, project):
    if not Membership.objects.filter(project=project, user=user).exists():
        raise PermissionDenied("Projet introuvable.")
    conv, _ = Conversation.objects.get_or_create(project=project, defaults={"kind": Conversation.Kind.PROJECT})
    return conv


def direct_with(user, other):
    """Conversation directe avec `other`, réservée aux personnes qui partagent au moins un projet
    (sinon n'importe qui pourrait sonder la liste des comptes)."""
    if other.pk == user.pk:
        raise ValidationError("Vous ne pouvez pas vous écrire à vous-même : utilisez le bloc-notes de votre projet.")
    shared = Membership.objects.filter(user=user, project__membership__user=other).exists()
    if not shared or not other.is_active:
        raise PermissionDenied("Vous ne pouvez écrire qu'aux personnes qui partagent un projet avec vous.")
    a, b = sorted([user, other], key=lambda u: u.pk)
    conv, _ = Conversation.objects.get_or_create(user_a=a, user_b=b, defaults={"kind": Conversation.Kind.DIRECT})
    return conv


# ------------------------------------------------------------------ messages
def parse_mentions(content, people, author):
    """(utilisateurs mentionnés, @tous ?) — seuls les participants comptent, jamais l'auteur."""
    by_name = {u.username.lower(): u for u in people}
    found, everyone = {}, False
    for name in MENTION.findall(content):
        key = name.lower()
        if key in EVERYONE and len(people) > 2:
            everyone = True
        elif key in by_name:
            found[by_name[key].pk] = by_name[key]
    if everyone:
        found.update({u.pk: u for u in people})
    found.pop(author.pk, None)
    return list(found.values()), everyone


@transaction.atomic
def post_message(user, conv, content):
    if not can_write(user, conv):
        raise PermissionDenied("Vous ne pouvez pas écrire dans cette conversation.")
    content = (content or "").strip()
    if not content:
        raise ValidationError("Le message est vide.")
    if len(content) > MAX_LENGTH:
        raise ValidationError(f"Message trop long ({MAX_LENGTH} caractères au plus).")
    msg = Message.objects.create(conversation=conv, author=user, content=content)
    people = participants(conv)
    mentioned, everyone = parse_mentions(content, people, user)
    if mentioned:
        msg.mentions.set(mentioned)
        Notification.objects.bulk_create([Notification(user=u, message=msg) for u in mentioned])
    if everyone:
        Message.objects.filter(pk=msg.pk).update(mentions_all=True)
        msg.mentions_all = True
    mark_read(user, conv, msg.pk)
    return msg


def delete_message(user, msg):
    conv = msg.conversation
    owner = conv.kind == Conversation.Kind.PROJECT and _role(user, conv) == Membership.Role.OWNER
    if msg.author_id != user.pk and not owner:
        raise PermissionDenied("Vous ne pouvez supprimer que vos propres messages.")
    msg.delete()


def can_delete(user, msg):
    conv = msg.conversation
    return msg.author_id == user.pk or (conv.kind == Conversation.Kind.PROJECT and _role(user, conv) == Membership.Role.OWNER)


def history(conv, after=None, before=None, limit=PAGE):
    """Messages d'un fil : les plus récents par défaut ; `after` = seulement les nouveaux (rafraîchissement),
    `before` = page précédente. Toujours renvoyés du plus ancien au plus récent."""
    qs = conv.messages.select_related("author").prefetch_related("mentions")
    limit = max(1, min(int(limit or PAGE), 100))
    if after:
        return list(qs.filter(pk__gt=int(after))[:200]), False
    if before:
        qs = qs.filter(pk__lt=int(before))
    page = list(qs.order_by("-id")[: limit + 1])
    return page[:limit][::-1], len(page) > limit


# ------------------------------------------------------------------ lu / non lu
def mark_read(user, conv, upto=None):
    if upto is None:  # ouvrir le fil = avoir vu les mentions qui s'y trouvent
        Notification.objects.filter(user=user, message__conversation=conv, read_at__isnull=True).update(read_at=timezone.now())
    last = upto or conv.messages.aggregate(m=Max("id"))["m"] or 0
    mark, _ = ReadMark.objects.get_or_create(conversation=conv, user=user)
    if last > mark.last_read_id:
        mark.last_read_id = last
        mark.save(update_fields=["last_read_id"])


def unread_counts(user, conv_ids):
    """{conversation_id: nombre de messages des autres après mon dernier message lu}."""
    marks = dict(ReadMark.objects.filter(user=user, conversation_id__in=conv_ids).values_list("conversation_id", "last_read_id"))
    counts = {}
    for cid in conv_ids:
        counts[cid] = Message.objects.filter(conversation_id=cid, id__gt=marks.get(cid, 0)).exclude(author=user).count()
    return counts


def my_conversations(user):
    """Fils de tous mes projets (créés à la demande) + mes conversations directes."""
    for project in Project.objects.filter(membership__user=user):
        Conversation.objects.get_or_create(project=project, defaults={"kind": Conversation.Kind.PROJECT})
    return list(Conversation.objects.filter(
        Q(project__membership__user=user) | Q(user_a=user) | Q(user_b=user)).distinct().select_related("project", "user_a", "user_b"))


def last_messages(conv_ids):
    out = {}
    for m in Message.objects.filter(conversation_id__in=conv_ids).order_by("conversation_id", "-id").select_related("author"):
        out.setdefault(m.conversation_id, m)
    return out


def summary(user):
    convs = my_conversations(user)
    unread = sum(unread_counts(user, [c.pk for c in convs]).values())
    return {"unread_messages": unread, "unread_notifications": Notification.objects.filter(user=user, read_at__isnull=True).count()}


# ------------------------------------------------------------------ notifications
def mark_notifications_read(user, ids=None):
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return qs.update(read_at=timezone.now())
