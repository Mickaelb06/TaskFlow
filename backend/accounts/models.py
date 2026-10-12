from django.conf import settings
from django.db import models


class SiteSettings(models.Model):
    """Réglages globaux modifiables par un administrateur (une seule ligne, pk=1)."""

    allow_registration = models.BooleanField(default=True)  # inscriptions publiques ouvertes

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class AuditLog(models.Model):
    """Trace de chaque action d'administration. Ne contient jamais de mot de passe."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    actor_name = models.CharField(max_length=150)  # conservé même si le compte est supprimé
    action = models.CharField(max_length=40)
    target = models.CharField(max_length=255, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Profile(models.Model):
    """Préférences de l'utilisateur. Le fuseau horaire pilote l'affichage du calendrier."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    timezone = models.CharField(max_length=64, default="Europe/Paris")  # nom IANA
    secondary_timezone = models.CharField(max_length=64, blank=True)  # 2e colonne d'heures (comme Notion Calendar)

    @classmethod
    def for_user(cls, user):
        obj, _ = cls.objects.get_or_create(user=user)
        return obj
