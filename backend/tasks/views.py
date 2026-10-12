from datetime import date, timedelta

from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.mixins import ProjectScopedMixin

from rest_framework.permissions import IsAuthenticated

from . import planning, services, time_services
from .models import Task, TimeEntry
from .serializers import CommentSerializer, TaskSerializer


class TaskViewSet(ProjectScopedMixin, viewsets.ModelViewSet):
    """Filtres : ?status=todo&assignee=3&due_after=2026-10-01&due_before=2026-10-31 (vue calendrier)."""

    serializer_class = TaskSerializer

    def get_queryset(self):
        qs = (Task.objects.filter(project=self.project).select_related("assignee").prefetch_related("dependencies")
              .annotate(time_total=Coalesce(Sum("time_entries__minutes"), 0)))
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


def _entry_data(e):
    return {"id": e.pk, "user": e.user.username if e.user else None, "user_id": e.user_id, "day": e.day, "minutes": e.minutes,
            "running": e.running, "started_at": e.started_at, "note": e.note}


class TimeView(ProjectScopedMixin, APIView):
    """GET : saisies de temps d'une tâche + total ; POST {minutes, day?, note?} : saisie manuelle."""

    def _task(self, task_pk):
        return get_object_or_404(Task, pk=task_pk, project=self.project)

    def get(self, request, project_pk, task_pk):
        task = self._task(task_pk)
        entries = task.time_entries.select_related("user")
        return Response({"total": time_services.total(task), "entries": [_entry_data(e) for e in entries[:100]]})

    def post(self, request, project_pk, task_pk):
        task = self._task(task_pk)
        day = request.data.get("day")
        try:
            day = date.fromisoformat(day) if day else None
        except ValueError:
            return Response({"day": "Date attendue (AAAA-MM-JJ)."}, status=400)
        e = time_services.add_manual(request.user, task, request.data.get("minutes"), day, str(request.data.get("note", "")))
        return Response(_entry_data(e), status=201)


class TimerStartView(ProjectScopedMixin, APIView):
    def post(self, request, project_pk, task_pk):
        task = get_object_or_404(Task, pk=task_pk, project=self.project)
        return Response(_entry_data(time_services.start(request.user, task)), status=201)


class TimeEntryView(ProjectScopedMixin, APIView):
    def delete(self, request, project_pk, task_pk, entry_pk):
        entry = get_object_or_404(TimeEntry.objects.select_related("task__project"), pk=entry_pk, task_id=task_pk, task__project=self.project)
        time_services.delete_entry(request.user, entry)
        return Response(status=204)


class TimerView(APIView):
    """Mon chrono en cours, tous projets confondus (affiché dans la barre latérale). POST /timer/stop/ l'arrête."""

    def get(self, request):
        e = time_services.running(request.user)
        return Response(None if e is None else {**_entry_data(e), "task": e.task_id, "task_title": e.task.title,
                                                "project": e.task.project_id, "project_name": e.task.project.name})

    def post(self, request):
        return Response(_entry_data(time_services.stop(request.user)))


class TimeReportView(ProjectScopedMixin, APIView):
    """GET /projects/{id}/time-report/?from=&to= (30 derniers jours par défaut)."""

    def get(self, request, project_pk):
        last = date.today()
        try:
            first = date.fromisoformat(request.query_params["from"]) if request.query_params.get("from") else last - timedelta(days=29)
            last = date.fromisoformat(request.query_params["to"]) if request.query_params.get("to") else last
        except ValueError:
            return Response({"detail": "Dates attendues au format AAAA-MM-JJ."}, status=400)
        if last < first or (last - first).days > 366:
            return Response({"detail": "Période invalide (un an au plus)."}, status=400)
        return Response(time_services.report(self.project, first, last))


class WorkloadView(ProjectScopedMixin, APIView):
    """GET /projects/{id}/workload/?weeks=4 — charge par membre et par semaine, propositions de rééquilibrage."""

    def get(self, request, project_pk):
        try:
            weeks = min(max(int(request.query_params.get("weeks", 4)), 1), 12)
        except ValueError:
            return Response({"weeks": "Nombre entier attendu."}, status=400)
        return Response(planning.workload(self.project, weeks))


class SimulateView(ProjectScopedMixin, APIView):
    """GET /projects/{id}/simulate/?delay=3 — si une tâche prenait `delay` jours de plus, de combien la fin reculerait-elle ?"""

    def get(self, request, project_pk):
        try:
            delay = int(request.query_params.get("delay", 3))
        except ValueError:
            delay = 0
        if not 1 <= delay <= 60:
            return Response({"delay": "Entre 1 et 60 jours."}, status=400)
        return Response(planning.delay_simulation(self.project, delay))


class DashboardView(APIView):
    """Tableau de bord personnel : mes tâches, mes projets et leur santé, alertes d'équipe."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(planning.user_dashboard(request.user))
