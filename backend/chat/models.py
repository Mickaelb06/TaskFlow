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
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    edited_at = models.DateTimeField(null=True, blank=True)
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


class Reaction(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="reactions")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    emoji = models.CharField(max_length=8)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.UniqueConstraint(fields=["message", "user", "emoji"], name="one_reaction_per_emoji")]


def attachment_path(instance, filename):
    """Nom stocké = identifiant aléatoire : le nom envoyé par l'utilisateur ne touche jamais au système de fichiers."""
    import uuid
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"chat/{uuid.uuid4().hex}.{ext}"


class Attachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    name = models.CharField(max_length=200)  # nom d'origine, affiché seulement
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


from django.db.models.signals import post_delete  # noqa: E402
from django.dispatch import receiver  # noqa: E402


@receiver(post_delete, sender=Attachment)
def _remove_file(sender, instance, **kwargs):
    """Un fichier ne survit pas à son message (suppression directe, du projet ou du compte)."""
    instance.file.delete(save=False)
