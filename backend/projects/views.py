from datetime import date

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import services, templates
from .mixins import ProjectScopedMixin
from .models import Membership, Project, ProjectTemplate
from .serializers import (AddMemberSerializer, CreateInviteSerializer, InviteSerializer, MembershipSerializer,
                          ProjectSerializer, RoleSerializer)


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

    @action(detail=True, methods=["post"], url_path="save-template")
    def save_template(self, request, pk=None):
        """POST /projects/{id}/save-template/ {name, description?} — enregistrer la structure comme modèle (propriétaire)."""
        tpl = templates.save_as_template(request.user, self.get_object(), request.data.get("name"), str(request.data.get("description", "")))
        return Response({"id": tpl.pk, "name": tpl.name, "tasks": len(tpl.tasks)}, status=201)

    @action(detail=True, methods=["post"])
    def transfer(self, request, pk=None):
        """POST /projects/{id}/transfer/ {user_id} — céder la propriété à un membre."""
        project = self.get_object()
        services.transfer_to_member(request.user, project, request.data.get("user_id"))
        return Response(ProjectSerializer(project, context={"request": request}).data)


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


class TemplateListView(APIView):
    """GET /templates/ — modèles fournis + les miens."""

    def get(self, request):
        return Response(templates.catalog(request.user))


class TemplateDetailView(APIView):
    def delete(self, request, pk):
        tpl = get_object_or_404(ProjectTemplate, pk=pk, owner=request.user)  # le modèle d'un autre : 404
        templates.delete_template(request.user, tpl)
        return Response(status=204)


class FromTemplateView(APIView):
    """POST {template, name?, start_date?} — crée un projet depuis un modèle."""

    def post(self, request):
        try:
            start = date.fromisoformat(request.data["start_date"]) if request.data.get("start_date") else None
        except ValueError:
            return Response({"start_date": "Date attendue (AAAA-MM-JJ)."}, status=400)
        project = templates.create_from_template(request.user, request.data.get("template"), request.data.get("name"), start)
        return Response(ProjectSerializer(project, context={"request": request}).data, status=201)


class ProjectInviteView(ProjectScopedMixin, APIView):
    """GET : liens actifs du projet ; POST : en créer un (le jeton n'est renvoyé qu'ici). Propriétaire seulement."""

    write_roles = (Membership.Role.OWNER,)

    def get(self, request, project_pk):
        return Response(InviteSerializer(services.list_invites(request.user, self.project), many=True).data)

    def post(self, request, project_pk):
        data = CreateInviteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invite, token = services.create_invite(request.user, self.project, **data.validated_data)
        return Response({**InviteSerializer(invite).data, "token": token}, status=status.HTTP_201_CREATED)


class ProjectInviteDetailView(ProjectScopedMixin, APIView):
    write_roles = (Membership.Role.OWNER,)

    def delete(self, request, project_pk, invite_id):
        services.revoke_invite(request.user, self.project, invite_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitePreviewView(APIView):
    """GET /invites/{jeton}/ : public (la page d'inscription annonce le projet). 404 identique pour tout jeton non valable."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "invite"

    def get(self, request, token):
        invite = services.find_invite(token)
        return Response({"project_name": invite.project.name, "role": invite.role,
                         "inviter": invite.created_by.username if invite.created_by else None})


class InviteAcceptView(APIView):
    throttle_scope = "invite"

    def post(self, request, token):
        project, already = services.accept_invite(request.user, token)
        return Response({"project_id": project.pk, "project_name": project.name, "already_member": already})


class MemberCandidatesView(ProjectScopedMixin, APIView):
    """GET /projects/{id}/member-candidates/?q=le : propositions pour l'ajout par nom (propriétaire seulement)."""

    write_roles = (Membership.Role.OWNER,)
    throttle_scope = "search"

    def get(self, request, project_pk):
        users = services.search_candidates(request.user, self.project, request.query_params.get("q"))
        return Response([{"id": u.pk, "username": u.username} for u in users])
