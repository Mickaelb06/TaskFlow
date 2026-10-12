from django.urls import path

from . import admin_views as admin
from .views import ExportView, LoginView, MeView, PublicConfigView, RegisterView

urlpatterns = [
    path("auth/register/", RegisterView.as_view()),
    path("auth/config/", PublicConfigView.as_view()),
    path("auth/token/", LoginView.as_view()),
    path("me/", MeView.as_view()),
    path("me/export/", ExportView.as_view()),
    # --- administration (réservée aux comptes is_staff)
    path("admin/stats/", admin.StatsView.as_view()),
    path("admin/users/", admin.UserListCreateView.as_view()),
    path("admin/users/<int:pk>/", admin.UserDetailView.as_view()),
    path("admin/users/<int:pk>/reset-password/", admin.ResetPasswordView.as_view()),
    path("admin/projects/", admin.ProjectListView.as_view()),
    path("admin/projects/<int:pk>/", admin.ProjectDetailView.as_view()),
    path("admin/projects/<int:pk>/transfer/", admin.ProjectTransferView.as_view()),
    path("admin/audit/", admin.AuditListView.as_view()),
    path("admin/settings/", admin.SettingsView.as_view()),
]
