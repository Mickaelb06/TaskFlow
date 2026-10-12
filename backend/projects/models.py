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


class ProjectTemplate(models.Model):
    """Modèle de projet personnel : une liste de tâches avec des décalages relatifs au démarrage (voir `templates.py`)."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_templates")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    skip_weekends = models.BooleanField(default=False)
    tasks = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]


class ProjectInvite(models.Model):
    """Lien d'invitation à un projet. Le jeton n'est jamais stocké : seule son empreinte l'est (comme un mot de passe),
    il n'est montré qu'à la création. Un lien expire, a un nombre d'usages maximal et peut être révoqué."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invites")
    token_hash = models.CharField(max_length=64, unique=True)
    role = models.CharField(max_length=10, choices=[("member", "Membre"), ("viewer", "Lecteur")], default="member")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    max_uses = models.PositiveSmallIntegerField(default=10)
    uses = models.PositiveSmallIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at", "-id"]
