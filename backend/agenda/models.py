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
    recurrence = models.CharField(max_length=8, blank=True, choices=[("daily", "Tous les jours"), ("weekdays", "Jours ouvrés"),
                                                                      ("weekly", "Toutes les semaines"), ("monthly", "Tous les mois")])
    recurrence_until = models.DateField(null=True, blank=True)  # dernier jour (inclus) ; vide = sans fin (borné à 3 ans par le service)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at", "id"]
        constraints = [models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="event_ends_after_start")]
        indexes = [models.Index(fields=["starts_at"])]

    def __str__(self):
        return self.title


class EventSkip(models.Model):
    """Occurrence supprimée d'un événement récurrent (jour local de l'occurrence dans le fuseau de l'événement)."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="skips")
    day = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["event", "day"], name="one_skip_per_day")]


class Invitation(models.Model):
    """Invité à un événement : voit l'événement, répond (accepté / refusé) et reçoit une notification."""

    class Status(models.TextChoices):
        INVITED = "invited", "Invité"
        ACCEPTED = "accepted", "Accepté"
        DECLINED = "declined", "Refusé"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="invitations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invitations")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.INVITED)
    seen_at = models.DateTimeField(null=True, blank=True)  # notification lue
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="one_invitation_per_user")]
