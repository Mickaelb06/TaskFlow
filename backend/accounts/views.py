from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.views import TokenObtainPairView

from . import account_services
from .models import Profile, SiteSettings

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    throttle_scope = "register"
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        if not SiteSettings.get().allow_registration:
            raise PermissionDenied("Les inscriptions sont fermées. Contactez un administrateur.")
        return super().create(request, *args, **kwargs)


class LoginView(TokenObtainPairView):
    """Connexion JWT, limitée par adresse IP : freine les essais de mots de passe en rafale."""

    throttle_scope = "login"


class MeView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = UserSerializer
    throttle_scope = "account"

    def get_throttles(self):  # seule la suppression est limitée : changer de fuseau reste libre
        return super().get_throttles() if self.request.method == "DELETE" else []

    def delete(self, request, *args, **kwargs):
        """Supprime SON compte (RGPD) : mot de passe exigé, voir `account_services.delete_account`."""
        account_services.delete_account(request.user, request.data.get("password", ""))
        return Response(status=204)

    def get_object(self):
        Profile.for_user(self.request.user)  # crée les préférences à la première lecture
        return self.request.user


class PublicConfigView(APIView):
    """Réglages publics utiles à l'écran de connexion."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"registration_open": SiteSettings.get().allow_registration})


class ExportView(APIView):
    """Toutes les données personnelles de l'utilisateur, en JSON (droit d'accès / portabilité)."""

    throttle_scope = "account"

    def get(self, request):
        response = Response(account_services.export_data(request.user))
        response["Content-Disposition"] = 'attachment; filename="taskflow-mes-donnees.json"'
        return response
