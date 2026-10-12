from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (FromTemplateView, InviteAcceptView, InvitePreviewView, MemberCandidatesView, MemberViewSet, ProjectInviteDetailView,
                    ProjectInviteView, ProjectViewSet, TemplateDetailView, TemplateListView)

router = DefaultRouter()
router.register("projects", ProjectViewSet, basename="project")

urlpatterns = [
    path("templates/", TemplateListView.as_view()),
    path("templates/<int:pk>/", TemplateDetailView.as_view()),
    path("projects/from-template/", FromTemplateView.as_view()),
] + router.urls + [
    path("projects/<int:project_pk>/members/", MemberViewSet.as_view({"get": "list", "post": "create"})),
    path(
        "projects/<int:project_pk>/members/<int:user_id>/",
        MemberViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
    ),
    path("projects/<int:project_pk>/invites/", ProjectInviteView.as_view()),
    path("projects/<int:project_pk>/invites/<int:invite_id>/", ProjectInviteDetailView.as_view()),
    path("projects/<int:project_pk>/member-candidates/", MemberCandidatesView.as_view()),
    path("invites/<str:token>/", InvitePreviewView.as_view()),
    path("invites/<str:token>/accept/", InviteAcceptView.as_view()),
]
