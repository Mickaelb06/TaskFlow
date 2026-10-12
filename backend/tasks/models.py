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
    # tâche récurrente : quand on la termine, la suivante est créée (voir services._spawn_next)
    recurrence = models.CharField(max_length=8, blank=True, choices=[("daily", "Tous les jours"), ("weekdays", "Jours ouvrés"),
                                                                      ("weekly", "Toutes les semaines"), ("monthly", "Tous les mois")])
    recurrence_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="recurrences")
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


class TimeEntry(models.Model):
    """Temps passé sur une tâche. Un chrono en cours a `started_at` et pas encore de `minutes` ; une saisie manuelle
    a des `minutes` et pas de `started_at`. `day` (jour local) sert aux rapports."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="time_entries")  # null = compte supprimé
    day = models.DateField()
    minutes = models.PositiveIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-day", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(minutes__isnull=False) | models.Q(started_at__isnull=False), name="timeentry_running_or_done"),
            models.CheckConstraint(condition=models.Q(minutes__isnull=True) | models.Q(minutes__lte=1440), name="timeentry_max_one_day"),
        ]

    @property
    def running(self):
        return self.minutes is None
