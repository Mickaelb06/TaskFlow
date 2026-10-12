
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from projects.models import Project
from tasks import planning_engine

from . import admin_services as svc
from .models import AuditLog, SiteSettings
from .permissions import IsAppAdmin

User = get_user_model()


class AdminAPIView(APIView):
    permission_classes = [IsAppAdmin]


# ------------------------------------------------------------ sérialisation
class AdminUserSerializer(serializers.ModelSerializer):
    project_count = serializers.IntegerField(read_only=True, default=0)
    owned_count = serializers.IntegerField(read_only=True, default=0)
    open_tasks = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_active", "is_staff", "is_superuser", "date_joined", "last_login",
                  "project_count", "owned_count", "open_tasks"]


class CreateUserSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[\w.@+-]+$", max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)
    is_staff = serializers.BooleanField(default=False)


class UpdateUserSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    is_active = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)


class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(required=False, allow_blank=True, write_only=True)


class TransferSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()


class SettingsSerializer(serializers.Serializer):
    allow_registration = serializers.BooleanField(required=False)


class AuditSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "actor_name", "action", "target", "details", "created_at"]


def one_user(pk):
    return get_object_or_404(svc.user_queryset(), pk=pk)


# ------------------------------------------------------------ vues
class StatsView(AdminAPIView):
    def get(self, request):
        data = svc.stats()
        data["registration_open"] = SiteSettings.get().allow_registration
        data["planning_engine"] = {"name": planning_engine.NAME, "version": planning_engine.VERSION,
                                   "rust_available": planning_engine.RUST_AVAILABLE}
        return Response(data)


class UserListCreateView(AdminAPIView):
    def get(self, request):
        qs = svc.user_queryset().order_by("username")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q))
        flt = request.query_params.get("filter")
        if flt == "active":
            qs = qs.filter(is_active=True)
        elif flt == "inactive":
            qs = qs.filter(is_active=False)
        elif flt == "admin":
            qs = qs.filter(is_staff=True)
        return Response(AdminUserSerializer(qs[:500], many=True).data)

    def post(self, request):
        data = CreateUserSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user, generated = svc.create_user(request.user, **data.validated_data)
        body = AdminUserSerializer(one_user(user.pk)).data
        body["generated_password"] = generated  # affiché une seule fois, jamais stocké en clair
        return Response(body, status=status.HTTP_201_CREATED)


class UserDetailView(AdminAPIView):
    def get(self, request, pk):
        user = one_user(pk)
        body = AdminUserSerializer(user).data
        body["owned_projects"] = svc.owned_projects_info(user)
        return Response(body)

    def patch(self, request, pk):
        data = UpdateUserSerializer(data=request.data, partial=True)  # un champ absent ne doit rien modifier
        data.is_valid(raise_exception=True)
        svc.update_user(request.user, get_object_or_404(User, pk=pk), **data.validated_data)
        return Response(AdminUserSerializer(one_user(pk)).data)

    def delete(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        raw = request.query_params.get("transfer_to")
        try:
            svc.delete_user(request.user, target, transfer_to=int(raw) if raw else None,
                            delete_solo=request.query_params.get("delete_solo") == "1")
        except svc.NeedsTransfer as e:
            return Response({"detail": "Cet utilisateur possède des projets : choisissez un repreneur.",
                             "owned_projects": e.projects}, status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResetPasswordView(AdminAPIView):
    def post(self, request, pk):
        data = PasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        generated = svc.reset_password(request.user, get_object_or_404(User, pk=pk), data.validated_data.get("password"))
        return Response({"generated_password": generated})


class ProjectListView(AdminAPIView):
    def get(self, request):
        qs = Project.objects.select_related("owner").annotate(
            member_count=Count("membership", distinct=True), task_count=Count("tasks", distinct=True),
            done_count=Count("tasks", filter=Q(tasks__status="done"), distinct=True)).order_by("name")
        q = request.query_params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(owner__username__icontains=q))
        return Response([{"id": p.pk, "name": p.name, "owner": p.owner.username, "owner_id": p.owner_id,
                          "members": p.member_count, "tasks": p.task_count, "done": p.done_count,
                          "deadline": p.deadline, "created_at": p.created_at} for p in qs[:500]])


class ProjectDetailView(AdminAPIView):
    def delete(self, request, pk):
        svc.delete_project(request.user, get_object_or_404(Project, pk=pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectTransferView(AdminAPIView):
    def post(self, request, pk):
        data = TransferSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        project = svc.transfer_project(request.user, get_object_or_404(Project, pk=pk), data.validated_data["user_id"])
        return Response({"id": project.pk, "owner": project.owner.username})


class AuditListView(AdminAPIView):
    def get(self, request):
        qs = AuditLog.objects.all()
        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action__startswith=action)
        limit = min(int(request.query_params.get("limit", 100) or 100), 500)
        return Response(AuditSerializer(qs[:limit], many=True).data)


class SettingsView(AdminAPIView):
    def get(self, request):
        s = SiteSettings.get()
        return Response({"allow_registration": s.allow_registration})

    def patch(self, request):
        data = SettingsSerializer(data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        s = svc.update_settings(request.user, **data.validated_data)
        return Response({"allow_registration": s.allow_registration})
