from django.urls import path

from .views import (
    CommentViewSet, DashboardView, InsightsView, ReplanView, TaskViewSet,
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
    path("projects/<int:project_pk>/replan/", ReplanView.as_view()),
]
