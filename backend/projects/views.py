from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from . import services
from .mixins import ProjectScopedMixin
from .models import Membership, Project
from .serializers import AddMemberSerializer, MembershipSerializer, ProjectSerializer, RoleSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        # Un utilisateur ne voit que les projets dont il est membre
        return Project.objects.filter(membership__user=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = services.create_project(
            self.request.user,
            serializer.validated_data["name"],
            serializer.validated_data.get("description", ""),
            serializer.validated_data.get("deadline"),
        )

    def _require_owner(self, project):
        if services.get_role(self.request.user, project) != Membership.Role.OWNER:
            raise PermissionDenied("Réservé au propriétaire du projet.")

    def perform_update(self, serializer):
        self._require_owner(serializer.instance)
        serializer.save()

    def perform_destroy(self, instance):
        self._require_owner(instance)
        instance.delete()


class MemberViewSet(
    ProjectScopedMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Gestion des membres : lecture pour tous les membres, écriture réservée au propriétaire.
    Exception : n'importe quel membre peut quitter le projet (DELETE sur soi-même)."""

    serializer_class = MembershipSerializer
    lookup_field = "user_id"
    lookup_url_kwarg = "user_id"

    def initial(self, request, *args, **kwargs):
        # DELETE sur soi-même autorisé quel que soit le rôle
        if request.method == "DELETE" and str(kwargs.get("user_id")) == str(getattr(request.user, "id", None)):
            self.write_roles = tuple(Membership.Role.values)
        super().initial(request, *args, **kwargs)

    write_roles = (Membership.Role.OWNER,)

    def get_queryset(self):
        return Membership.objects.filter(project=self.project).select_related("user").order_by("user__username")

    def create(self, request, *args, **kwargs):
        data = AddMemberSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = services.add_member(request.user, self.project, **data.validated_data)
        return Response(MembershipSerializer(membership).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        membership = self.get_object()
        data = RoleSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        membership = services.change_role(request.user, membership, data.validated_data["role"])
        return Response(MembershipSerializer(membership).data)

    def perform_destroy(self, instance):
        services.remove_member(self.request.user, instance)
