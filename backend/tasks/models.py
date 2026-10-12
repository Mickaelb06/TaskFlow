from django.conf import settings
from django.db import models


class Task(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "À faire"
        DOING = "doing", "En cours"
        DONE = "done", "Terminée"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.TODO)
    priority = models.PositiveSmallIntegerField(default=2)  # 1 haute, 2 normale, 3 basse
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)  # fin de la tâche (échéance)
    is_milestone = models.BooleanField(default=False)  # jalon : affiché en losange dans le Gantt
    # « cette tâche dépend de… » : elle ne peut pas commencer avant la fin de ses prédécesseurs
    dependencies = models.ManyToManyField("self", symmetrical=False, related_name="dependents", blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tasks"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)  # renseignée quand la tâche passe à « terminée »

    class Meta:
        ordering = ["priority", "due_date"]
        constraints = [
            models.CheckConstraint(condition=models.Q(priority__gte=1, priority__lte=3), name="task_priority_1_3"),
            models.CheckConstraint(
                condition=models.Q(start_date__isnull=True)
                | models.Q(due_date__isnull=True)
                | models.Q(start_date__lte=models.F("due_date")),
                name="task_start_before_due",
            ),
        ]


class Comment(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)  # null = compte supprimé
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
