from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Conversation(models.Model):
    """Un fil de discussion : celui d'un projet (équipe, ou bloc-notes si le projet est solo)
    ou une conversation directe entre deux personnes (`user_a.pk < user_b.pk`, jamais en double)."""

    class Kind(models.TextChoices):
        PROJECT = "project", "Projet"
        DIRECT = "direct", "Direct"

    kind = models.CharField(max_length=8, choices=Kind.choices)
    project = models.OneToOneField("projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="conversation")
    user_a = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    user_b = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="conversation_shape", condition=(
                Q(kind="project", project__isnull=False, user_a__isnull=True, user_b__isnull=True)
                | Q(kind="direct", project__isnull=True, user_a__isnull=False, user_b__isnull=False, user_a__lt=F("user_b")))),
            models.UniqueConstraint(fields=["user_a", "user_b"], name="direct_pair_unique"),
        ]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    content = models.TextField(max_length=2000)
    mentions = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="+")
    mentions_all = models.BooleanField(default=False)  # « @tous »
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["conversation", "id"])]


class ReadMark(models.Model):
    """Dernier message lu par un utilisateur dans une conversation (sert aux pastilles « non lus »)."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    last_read_id = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="one_readmark_per_user")]


class Notification(models.Model):
    """Quelqu'un vous a mentionné avec @. Supprimée avec le message."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="notifications")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.UniqueConstraint(fields=["user", "message"], name="one_notification_per_message")]
