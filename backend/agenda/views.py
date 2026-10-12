from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import CalendarTaskSerializer, EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    """Événements visibles par l'utilisateur (les siens + ceux de ses projets). Les droits d'écriture
    sont vérifiés dans `services`."""

    serializer_class = EventSerializer

    def get_queryset(self):
        return services.visible_events(self.request.user).select_related("project", "creator").prefetch_related("invitations__user")

    def perform_create(self, serializer):
        serializer.instance = services.create_event(self.request.user, **serializer.validated_data)

    def perform_update(self, serializer):
        services.update_event(self.request.user, serializer.instance, **serializer.validated_data)

    def perform_destroy(self, instance):
        services.delete_event(self.request.user, instance)


class CalendarView(APIView):
    """GET /api/calendar/?from=2026-10-12&to=2026-10-18[&project=3][&mine=1]
    Les jours sont ceux du fuseau horaire du profil de l'utilisateur."""

    def get(self, request):
        first, last = services.parse_range(request.query_params.get("from"), request.query_params.get("to"))
        project = None
        if request.query_params.get("project"):
            project = services.member_project(request.user, request.query_params["project"])
            if project is None:
                raise NotFound("Projet introuvable.")
        events, tasks = services.calendar(request.user, first, last, project, request.query_params.get("mine") == "1")
        ctx = {"request": request}
        return Response({
            "timezone": services.user_zone(request.user).key,
            "events": EventSerializer(events, many=True, context=ctx).data,
            "tasks": CalendarTaskSerializer(tasks, many=True).data,
        })


class RsvpView(APIView):
    """POST {status: accepted | declined} — répondre à une invitation."""

    def post(self, request, pk):
        event = get_object_or_404(services.visible_events(request.user), pk=pk)
        services.rsvp(request.user, event, request.data.get("status"))
        event = services.visible_events(request.user).prefetch_related("invitations__user").get(pk=pk)
        return Response(EventSerializer(event, context={"request": request}).data)


class SkipView(APIView):
    """POST {day: AAAA-MM-JJ} — supprimer une seule occurrence d'une série."""

    def post(self, request, pk):
        event = get_object_or_404(services.visible_events(request.user), pk=pk)
        services.skip_occurrence(request.user, event, request.data.get("day"))
        return Response(status=204)


class ContactsView(APIView):
    """Personnes que je peux inviter : celles qui partagent un de mes projets."""

    def get(self, request):
        return Response([{"id": u.pk, "username": u.username} for u in services.contacts(request.user).order_by("username")])
