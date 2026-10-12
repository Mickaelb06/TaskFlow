from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Membership
from taskflow.throttles import WritesOnlyThrottle

from . import services
from .models import Attachment, Conversation, Message, Notification

User = get_user_model()
PREVIEW = 90


def _user(u):
    return {"id": u.pk, "username": u.username} if u else None


def _excerpt(text, n=PREVIEW):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def conversation_data(user, conv, unread=0, last=None):
    members = services.participants(conv)
    direct = conv.kind == Conversation.Kind.DIRECT
    other = next((u for u in members if u.pk != user.pk), None) if direct else None
    return {
        "id": conv.pk, "kind": conv.kind,
        "title": other.username if direct else conv.project.name,
        "project": conv.project_id, "other": _user(other),
        "solo": (not direct) and len(members) == 1,  # projet solo : le fil sert de bloc-notes, personne à mentionner
        "can_write": services.can_write(user, conv),
        "members": [_user(u) for u in members],
        "unread": unread,
        "last": {"author": last.author.username if last and last.author else None, "excerpt": _excerpt(last.content),
                 "created_at": last.created_at} if last else None,
    }


def messages_payload(user, conv, msgs):
    """Messages prêts à sérialiser : un seul passage pour les tâches citées, réactions et pièces jointes."""
    refs = services.task_refs(conv, msgs)
    out = []
    for msg in msgs:
        by_emoji = {}
        for r in msg.reactions.all():
            by_emoji.setdefault(r.emoji, []).append(r.user.username)
        parent = msg.reply_to
        out.append({
            "id": msg.pk, "author": _user(msg.author), "content": msg.content, "created_at": msg.created_at,
            "edited": msg.edited_at is not None,
            "mentions": [u.username for u in msg.mentions.all()], "mentions_all": msg.mentions_all,
            "can_delete": services.can_delete(user, msg), "can_edit": msg.author_id == user.pk and services.can_write(user, conv),
            "reply_to": {"id": parent.pk, "author": parent.author.username if parent.author else None, "excerpt": _excerpt(parent.content or "Pièce jointe", 120)} if parent else None,
            "reactions": [{"emoji": e, "count": len(names), "mine": user.username in names, "users": names} for e, names in by_emoji.items()],
            "attachments": [{"id": a.pk, "name": a.name, "size": a.size, "content_type": a.content_type,
                             "image": a.content_type.startswith("image/")} for a in msg.attachments.all()],
            "tasks": [{"id": t.pk, "title": t.title, "status": t.status, "project": t.project_id} for t in refs.get(msg.pk, [])],
        })
    return out


def _prefetched(qs):
    return qs.select_related("author", "reply_to__author").prefetch_related("mentions", "reactions__user", "attachments")


def _conversation_or_404(user, pk):
    conv = services.conversation_for(user, pk)
    if conv is None:
        raise NotFound("Conversation introuvable.")
    return conv


class ConversationListView(APIView):
    def get(self, request):
        convs = services.my_conversations(request.user)
        ids = [c.pk for c in convs]
        unread, last = services.unread_counts(request.user, ids), services.last_messages(ids)
        rows = [conversation_data(request.user, c, unread[c.pk], last.get(c.pk)) for c in convs]
        rows.sort(key=lambda r: r["last"]["created_at"].timestamp() if r["last"] else 0, reverse=True)  # fils actifs d'abord
        return Response(rows)


class DirectView(APIView):
    """POST {user: id | username} → la conversation directe (créée si besoin)."""

    def post(self, request):
        ref = request.data.get("user")
        other = User.objects.filter(pk=ref).first() if str(ref).isdigit() else User.objects.filter(username__iexact=str(ref or "")).first()
        if other is None:  # même réponse qu'un refus de partage : ne pas révéler quels comptes existent
            raise NotFound("Personne introuvable parmi vos collègues.")
        try:
            conv = services.direct_with(request.user, other)
        except PermissionDenied:  # même réponse que « inconnu » : impossible de deviner quels comptes existent
            raise NotFound("Personne introuvable parmi vos collègues.")
        return Response(conversation_data(request.user, conv))


class ContactsView(APIView):
    """Personnes avec qui je peux discuter : celles qui partagent un de mes projets."""

    def get(self, request):
        ids = Membership.objects.filter(project__membership__user=request.user).exclude(user=request.user).values_list("user", flat=True)
        users = User.objects.filter(pk__in=set(ids), is_active=True).order_by("username")
        return Response([_user(u) for u in users])


class MessagesView(APIView):
    throttle_classes = [WritesOnlyThrottle]
    throttle_scope = "chat"
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request, pk):
        conv = _conversation_or_404(request.user, pk)
        q = request.query_params
        try:
            msgs, more = services.history(conv, after=q.get("after"), before=q.get("before"), limit=q.get("limit"), around=q.get("around"))
        except ValueError:
            raise ValidationError("Paramètres invalides.")
        ids = [m.pk for m in msgs]
        msgs = list(_prefetched(Message.objects.filter(pk__in=ids)).order_by("id"))
        return Response({"messages": messages_payload(request.user, conv, msgs), "has_more": more})

    def post(self, request, pk):
        """JSON `{content, reply_to?}` ou multipart `content`, `reply_to`, `files` (3 au plus)."""
        conv = _conversation_or_404(request.user, pk)
        reply = request.data.get("reply_to")
        msg = services.post_message(request.user, conv, request.data.get("content"), reply_to=int(reply) if str(reply or "").isdigit() else None,
                                    files=request.FILES.getlist("files"))
        msg = _prefetched(Message.objects.filter(pk=msg.pk)).get()
        return Response(messages_payload(request.user, conv, [msg])[0], status=201)


class ReadView(APIView):
    def post(self, request, pk):
        services.mark_read(request.user, _conversation_or_404(request.user, pk))
        return Response({"ok": True})


def _message_or_404(user, pk):
    msg = Message.objects.select_related("conversation__project", "conversation__user_a", "conversation__user_b").filter(pk=pk).first()
    if msg is None or not services.can_read(user, msg.conversation):
        raise NotFound("Message introuvable.")
    return msg


class MessageDetailView(APIView):
    throttle_classes = [WritesOnlyThrottle]
    throttle_scope = "chat"

    def patch(self, request, pk):
        msg = _message_or_404(request.user, pk)
        services.edit_message(request.user, msg, request.data.get("content"))
        msg = _prefetched(Message.objects.filter(pk=msg.pk)).get()
        return Response(messages_payload(request.user, msg.conversation, [msg])[0])

    def delete(self, request, pk):
        services.delete_message(request.user, _message_or_404(request.user, pk))
        return Response(status=204)


class ReactionView(APIView):
    throttle_classes = [WritesOnlyThrottle]
    throttle_scope = "chat"

    def post(self, request, pk):
        """{emoji} : ajoute ma réaction, ou la retire si je l'avais déjà mise."""
        msg = _message_or_404(request.user, pk)
        services.toggle_reaction(request.user, msg, request.data.get("emoji"))
        msg = _prefetched(Message.objects.filter(pk=msg.pk)).get()
        return Response(messages_payload(request.user, msg.conversation, [msg])[0])


class AttachmentView(APIView):
    """Téléchargement d'une pièce jointe, réservé aux lecteurs de la conversation. Le type est celui vérifié à l'envoi,
    jamais celui du navigateur ; en-têtes anti-interprétation (nosniff, CSP sandbox)."""

    def get(self, request, pk):
        att = get_object_or_404(Attachment.objects.select_related("message__conversation__project", "message__conversation__user_a", "message__conversation__user_b"), pk=pk)
        if not services.can_read(request.user, att.message.conversation):
            raise NotFound("Fichier introuvable.")
        inline = att.content_type.startswith("image/")
        resp = FileResponse(att.file.open("rb"), content_type=att.content_type, as_attachment=not inline, filename=att.name)
        resp["X-Content-Type-Options"] = "nosniff"
        resp["Content-Security-Policy"] = "default-src 'none'; sandbox"
        resp["Cache-Control"] = "private, max-age=3600"
        return resp


class SearchView(APIView):
    """GET /chat/search/?q=mot[&conversation=id] — uniquement dans les conversations que je peux lire."""

    def get(self, request):
        conv = request.query_params.get("conversation")
        rows = services.search(request.user, request.query_params.get("q"), int(conv) if str(conv or "").isdigit() else None)
        return Response([{"message": m.pk, "conversation": c.pk, "conversation_title": conversation_data(request.user, c)["title"],
                          "author": m.author.username if m.author else None, "excerpt": _excerpt(m.content, 140), "created_at": m.created_at}
                         for m, c in rows])


class SummaryView(APIView):
    """Appelé toutes les ~15 s par le front pour les pastilles : deux nombres, rien d'autre."""

    def get(self, request):
        return Response(services.summary(request.user))


class NotificationsView(APIView):
    def get(self, request):
        rows = Notification.objects.filter(user=request.user).select_related(
            "message__author", "message__conversation__project", "message__conversation__user_a", "message__conversation__user_b")[:50]
        out = []
        for n in rows:
            conv, msg = n.message.conversation, n.message
            direct = conv.kind == Conversation.Kind.DIRECT
            other = (conv.user_b if conv.user_a_id == request.user.pk else conv.user_a) if direct else None
            out.append({
                "id": n.pk, "read": n.read_at is not None, "created_at": n.created_at,
                "conversation": conv.pk, "conversation_title": other.username if direct else conv.project.name,
                "message": msg.pk, "author": msg.author.username if msg.author else None, "excerpt": _excerpt(msg.content, 140),
                "everyone": msg.mentions_all,
            })
        return Response(out)

    def post(self, request):
        """{ids: [...]} ou {all: true}."""
        ids = None if request.data.get("all") else [int(i) for i in request.data.get("ids", []) if str(i).isdigit()]
        return Response({"marked": services.mark_notifications_read(request.user, ids)})
