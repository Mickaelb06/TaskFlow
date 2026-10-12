from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Profile, SiteSettings

from .serializers import RegisterSerializer, UserSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        if not SiteSettings.get().allow_registration:
            raise PermissionDenied("Les inscriptions sont fermées. Contactez un administrateur.")
        return super().create(request, *args, **kwargs)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        Profile.for_user(self.request.user)  # crée les préférences à la première lecture
        return self.request.user


class PublicConfigView(APIView):
    """Réglages publics utiles à l'écran de connexion."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({"registration_open": SiteSettings.get().allow_registration})
