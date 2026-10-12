from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Membership
from taskflow.throttles import WritesOnlyThrottle

from . import services
from .models import Conversation, Message, Notification

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


def message_data(user, msg):
    return {
        "id": msg.pk, "author": _user(msg.author), "content": msg.content, "created_at": msg.created_at,
        "mentions": [u.username for u in msg.mentions.all()], "mentions_all": msg.mentions_all,
        "can_delete": services.can_delete(user, msg),
    }


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

    def get(self, request, pk):
        conv = _conversation_or_404(request.user, pk)
        q = request.query_params
        try:
            msgs, more = services.history(conv, after=q.get("after"), before=q.get("before"), limit=q.get("limit"))
        except ValueError:
            raise ValidationError("Paramètres invalides.")
        return Response({"messages": [message_data(request.user, m) for m in msgs], "has_more": more})

    def post(self, request, pk):
        conv = _conversation_or_404(request.user, pk)
        msg = services.post_message(request.user, conv, request.data.get("content"))
        return Response(message_data(request.user, msg), status=201)


class ReadView(APIView):
    def post(self, request, pk):
        services.mark_read(request.user, _conversation_or_404(request.user, pk))
        return Response({"ok": True})


class MessageDeleteView(APIView):
    def delete(self, request, pk):
        msg = get_object_or_404(Message.objects.select_related("conversation"), pk=pk)
        if not services.can_read(request.user, msg.conversation):
            raise NotFound("Message introuvable.")
        services.delete_message(request.user, msg)
        return Response(status=204)


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
