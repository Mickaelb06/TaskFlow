"""Règles de la messagerie : qui lit, qui écrit, qui est mentionné, ce qui reste non lu."""
import re

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from projects.models import Membership, Project

from tasks.models import Task

from .models import Attachment, Conversation, Message, Notification, ReadMark, Reaction

User = get_user_model()
MAX_LENGTH = 2000
PAGE = 50
EVERYONE = ("tous", "all")
# « @nom » : pas collé à un mot (évite les emails), accepte nom.prenom, nom-x ; la ponctuation finale est exclue
REACTIONS = ("👍", "❤️", "😂", "🎉", "👀", "✅")
TASK_REF = re.compile(r"(?<![\w&])#(\d{1,9})\b")  # « #12 » désigne la tâche 12 du projet du fil
MAX_FILES, MAX_FILE_SIZE = 3, 5 * 1024 * 1024
# extension → (type MIME imposé, vérification du contenu). Le type envoyé par le navigateur n'est jamais cru ;
# pas de SVG ni de HTML (scripts), pas d'exécutables.
FILE_TYPES = {
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG")), ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")), ".gif": ("image/gif", lambda b: b.startswith(b"GIF8")),
    ".webp": ("image/webp", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"), ".pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    ".txt": ("text/plain; charset=utf-8", lambda b: b"\x00" not in b), ".csv": ("text/csv; charset=utf-8", lambda b: b"\x00" not in b),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", lambda b: b.startswith(b"PK\x03\x04")),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", lambda b: b.startswith(b"PK\x03\x04")),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", lambda b: b.startswith(b"PK\x03\x04")),
    ".odt": ("application/vnd.oasis.opendocument.text", lambda b: b.startswith(b"PK\x03\x04")),
}
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


def _check_file(f):
    name = (f.name or "fichier").replace("\\", "/").rsplit("/", 1)[-1][:200]
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in FILE_TYPES:
        raise ValidationError(f"Type de fichier non accepté : « {name} » (images, PDF, texte, CSV, documents Office).")
    if f.size > MAX_FILE_SIZE:
        raise ValidationError(f"« {name} » dépasse {MAX_FILE_SIZE // (1024 * 1024)} Mo.")
    head = f.read(16)
    f.seek(0)
    sniff = FILE_TYPES[ext][1]
    if f.size == 0 or not sniff(head if ext not in (".txt", ".csv") else f.read(65536)):
        f.seek(0)
        raise ValidationError(f"Le contenu de « {name} » ne correspond pas à son type.")
    f.seek(0)
    return name, ext


@transaction.atomic
def post_message(user, conv, content, reply_to=None, files=()):
    if not can_write(user, conv):
        raise PermissionDenied("Vous ne pouvez pas écrire dans cette conversation.")
    content = (content or "").strip()
    files = list(files)
    if not content and not files:
        raise ValidationError("Le message est vide.")
    if len(content) > MAX_LENGTH:
        raise ValidationError(f"Message trop long ({MAX_LENGTH} caractères au plus).")
    if len(files) > MAX_FILES:
        raise ValidationError(f"{MAX_FILES} fichiers au plus par message.")
    checked = [(f, *_check_file(f)) for f in files]
    parent = None
    if reply_to:
        parent = Message.objects.filter(pk=reply_to, conversation=conv).first()
        if parent is None:
            raise ValidationError("Le message cité n'existe pas dans cette conversation.")
    msg = Message.objects.create(conversation=conv, author=user, content=content, reply_to=parent)
    for f, name, ext in checked:
        Attachment.objects.create(message=msg, file=f, name=name, content_type=FILE_TYPES[ext][0], size=f.size)
    _notify(msg, user, conv, already=())
    mark_read(user, conv, msg.pk)
    return msg


def _notify(msg, author, conv, already):
    """Crée les notifications des personnes mentionnées qui ne l'étaient pas encore."""
    people = participants(conv)
    mentioned, everyone = parse_mentions(msg.content, people, author)
    fresh = [u for u in mentioned if u.pk not in already]
    if mentioned:
        msg.mentions.set(mentioned)
    if fresh:
        Notification.objects.bulk_create([Notification(user=u, message=msg) for u in fresh], ignore_conflicts=True)
    if everyone != msg.mentions_all:
        Message.objects.filter(pk=msg.pk).update(mentions_all=everyone)
        msg.mentions_all = everyone


@transaction.atomic
def edit_message(user, msg, content):
    """Seul l'auteur modifie son message ; les nouvelles mentions notifient, les anciennes ne sont pas renotifiées."""
    conv = msg.conversation
    if msg.author_id != user.pk or not can_write(user, conv):
        raise PermissionDenied("Vous ne pouvez modifier que vos propres messages.")
    content = (content or "").strip()
    if not content and not msg.attachments.exists():
        raise ValidationError("Le message est vide.")
    if len(content) > MAX_LENGTH:
        raise ValidationError(f"Message trop long ({MAX_LENGTH} caractères au plus).")
    before = set(msg.mentions.values_list("pk", flat=True))
    msg.content = content
    msg.edited_at = timezone.now()
    msg.save(update_fields=["content", "edited_at"])
    _notify(msg, user, conv, already=before)
    return msg


def toggle_reaction(user, msg, emoji):
    if emoji not in REACTIONS:
        raise ValidationError("Réaction non proposée.")
    if not can_write(user, msg.conversation):
        raise PermissionDenied("Vous ne pouvez pas réagir dans cette conversation.")
    existing = Reaction.objects.filter(message=msg, user=user, emoji=emoji)
    if existing.exists():
        existing.delete()
    else:
        Reaction.objects.create(message=msg, user=user, emoji=emoji)


def task_refs(conv, messages):
    """{id du message: [tâches citées avec #id]} — uniquement des tâches du projet du fil (jamais d'un autre projet)."""
    if conv.kind != Conversation.Kind.PROJECT:
        return {}
    wanted = {m.pk: {int(n) for n in TASK_REF.findall(m.content)} for m in messages}
    ids = set().union(*wanted.values()) if wanted else set()
    if not ids:
        return {}
    found = {t.pk: t for t in Task.objects.filter(project=conv.project, pk__in=ids)}
    return {mid: [found[i] for i in sorted(refs) if i in found] for mid, refs in wanted.items() if refs}


def search(user, query, conversation=None, limit=30):
    """Messages contenant `query` dans les conversations que je peux lire, du plus récent au plus ancien."""
    query = (query or "").strip()
    if len(query) < 2:
        raise ValidationError("Saisissez au moins 2 caractères.")
    convs = {c.pk: c for c in my_conversations(user)}
    ids = [conversation] if conversation and conversation in convs else list(convs)
    qs = Message.objects.filter(conversation_id__in=ids, content__icontains=query).select_related("author").order_by("-id")[:limit]
    return [(m, convs[m.conversation_id]) for m in qs]


def delete_message(user, msg):
    conv = msg.conversation
    owner = conv.kind == Conversation.Kind.PROJECT and _role(user, conv) == Membership.Role.OWNER
    if msg.author_id != user.pk and not owner:
        raise PermissionDenied("Vous ne pouvez supprimer que vos propres messages.")
    msg.delete()


def can_delete(user, msg):
    conv = msg.conversation
    return msg.author_id == user.pk or (conv.kind == Conversation.Kind.PROJECT and _role(user, conv) == Membership.Role.OWNER)


def history(conv, after=None, before=None, limit=PAGE, around=None):
    """Messages d'un fil : les plus récents par défaut ; `after` = seulement les nouveaux (rafraîchissement),
    `before` = page précédente. Toujours renvoyés du plus ancien au plus récent."""
    qs = conv.messages.select_related("author").prefetch_related("mentions")
    limit = max(1, min(int(limit or PAGE), 100))
    if around:  # résultat de recherche : le message visé, un peu avant et un peu après
        around = int(around)
        older = list(qs.filter(pk__lte=around).order_by("-id")[:21])
        newer = list(qs.filter(pk__gt=around).order_by("id")[:30])
        return older[:20][::-1] + newer, len(older) > 20
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
    from agenda.models import Invitation

    pending = Invitation.objects.filter(user=user, seen_at__isnull=True).count()  # invitations non vues = notifications aussi
    return {"unread_messages": unread, "unread_notifications": Notification.objects.filter(user=user, read_at__isnull=True).count() + pending}


# ------------------------------------------------------------------ notifications
def mark_notifications_read(user, ids=None, invitations=None):
    """`ids` : mentions ; `invitations` : invitations à des événements ; tous deux None = tout marquer comme lu."""
    from agenda.models import Invitation

    everything = ids is None and invitations is None
    qs = Notification.objects.filter(user=user, read_at__isnull=True)
    inv = Invitation.objects.filter(user=user, seen_at__isnull=True)
    if not everything:
        qs, inv = qs.filter(pk__in=ids or []), inv.filter(pk__in=invitations or [])
    return qs.update(read_at=timezone.now()) + inv.update(seen_at=timezone.now())
