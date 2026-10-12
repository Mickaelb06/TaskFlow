from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.mixins import ProjectScopedMixin

from rest_framework.permissions import IsAuthenticated

from . import planning, services
from .models import Task
from .serializers import CommentSerializer, TaskSerializer


class TaskViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """Filtres : ?status=todo&assignee=3&due_after=2026-10-01&due_before=2026-10-31 (vue calendrier)."""

    serializer_class = TaskSerializer

    def get_queryset(self):
        qs = Task.objects.filter(project=self.project).select_related("assignee").prefetch_related("dependencies")
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        if p.get("assignee"):
            qs = qs.filter(assignee_id=p["assignee"])
        if p.get("due_after"):
            qs = qs.filter(due_date__gte=p["due_after"])
        if p.get("due_before"):
            qs = qs.filter(due_date__lte=p["due_before"])
        return qs

    def perform_create(self, serializer):
        serializer.instance = services.create_task(self.request.user, self.project, **serializer.validated_data)

    def perform_update(self, serializer):
        serializer.instance = services.update_task(self.request.user, serializer.instance, serializer.validated_data)


class CommentViewSet(
    ProjectScopedMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CommentSerializer

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        self.task = get_object_or_404(Task, pk=kwargs["task_pk"], project=self.project)

    def get_queryset(self):
        return self.task.comments.select_related("author").order_by("created_at")

    def perform_create(self, serializer):
        serializer.instance = services.add_comment(self.request.user, self.task, serializer.validated_data["content"])


# ---------------------------------------------------------------- gestion de projet
class InsightsView(ProjectScopedMixin, APIView):
    """Indicateurs : avancement, fin prévue, chemin critique, risques, charge par membre."""

    def get(self, request, project_pk):
        return Response(planning.insights(self.project))


class ReplanView(ProjectScopedMixin, APIView):
    """Rattrape le retard : les tâches en retard redémarrent aujourd'hui, les dépendances suivent."""

    def post(self, request, project_pk):
        moved = planning.replan(self.project)
        return Response({"moved": moved})


class DashboardView(APIView):
    """Tableau de bord personnel : mes tâches, mes projets et leur santé, alertes d'équipe."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(planning.user_dashboard(request.user))
