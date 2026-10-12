from django.urls import path

from .views import (
    CommentViewSet, DashboardView, InsightsView, ReplanView, SimulateView, TaskViewSet, TimeEntryView, TimerStartView, TimerView, TimeReportView, TimeView, WorkloadView,
)

urlpatterns = [
    path("projects/<int:project_pk>/tasks/", TaskViewSet.as_view({"get": "list", "post": "create"})),
    path(
        "projects/<int:project_pk>/tasks/<int:pk>/",
        TaskViewSet.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}),
    ),
    path(
        "projects/<int:project_pk>/tasks/<int:task_pk>/comments/",
        CommentViewSet.as_view({"get": "list", "post": "create"}),
    ),
    path("dashboard/", DashboardView.as_view()),
    path("projects/<int:project_pk>/insights/", InsightsView.as_view()),
    path("projects/<int:project_pk>/tasks/<int:task_pk>/time/", TimeView.as_view()),
    path("projects/<int:project_pk>/tasks/<int:task_pk>/time/start/", TimerStartView.as_view()),
    path("projects/<int:project_pk>/tasks/<int:task_pk>/time/<int:entry_pk>/", TimeEntryView.as_view()),
    path("projects/<int:project_pk>/time-report/", TimeReportView.as_view()),
    path("timer/", TimerView.as_view()),
    path("projects/<int:project_pk>/workload/", WorkloadView.as_view()),
    path("projects/<int:project_pk>/simulate/", SimulateView.as_view()),
    path("projects/<int:project_pk>/replan/", ReplanView.as_view()),
]
