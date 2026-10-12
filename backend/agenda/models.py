from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Event(models.Model):
    """Rendez-vous avec une heure précise. Stocké en UTC ; le fuseau d'affichage est celui de l'utilisateur.

    `project` vide = événement personnel (visible de son créateur seul) ; sinon visible des membres du projet.
    `timezone` garde le fuseau dans lequel l'événement a été saisi (« 14 h à Tokyo »), à titre d'information."""

    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="events")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="event_ends_after_start")]
        indexes = [models.Index(fields=["starts_at"])]

    def __str__(self):
        return self.title
