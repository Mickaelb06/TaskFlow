from django.conf import settings
from django.db import models


class Project(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    deadline = models.DateField(null=True, blank=True)  # échéance du projet (comparée à la fin prévue)
    skip_weekends = models.BooleanField(default=False)  # durées et décalages en jours ouvrés (lundi-vendredi)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="owned_projects")
    created_at = models.DateTimeField(auto_now_add=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, through="Membership", related_name="projects")

    def __str__(self):
        return self.name


class Membership(models.Model):
    """Projet solo = un seul membre ; en équipe = plusieurs membres avec un rôle."""

    class Role(models.TextChoices):
        OWNER = "owner", "Propriétaire"
        MEMBER = "member", "Membre"
        VIEWER = "viewer", "Lecteur"

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["project", "user"], name="unique_member_per_project")]
