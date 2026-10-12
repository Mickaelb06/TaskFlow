from rest_framework import serializers

from projects.services import get_role

from . import planning, time_services
from .models import Comment, Task


class TaskSerializer(serializers.ModelSerializer):
    priority = serializers.IntegerField(min_value=1, max_value=3, default=2)
    assignee_name = serializers.CharField(source="assignee.username", read_only=True, default=None)
    dependencies = serializers.PrimaryKeyRelatedField(many=True, queryset=Task.objects.all(), required=False)
    time_minutes = serializers.SerializerMethodField()

    def get_time_minutes(self, obj):
        value = getattr(obj, "time_total", None)  # annoté par la vue de liste (une seule requête)
        return value if value is not None else time_services.total(obj)

    class Meta:
        model = Task
        fields = [
            "id", "project", "title", "description", "status", "priority",
            "start_date", "due_date", "is_milestone", "dependencies", "recurrence", "recurrence_of",
            "assignee", "assignee_name", "created_at", "completed_at", "time_minutes",
        ]
        read_only_fields = ["project", "created_at", "completed_at", "recurrence_of", "time_minutes"]

    def validate_assignee(self, value):
        project = self.context["view"].project
        if value is not None and get_role(value, project) is None:
            raise serializers.ValidationError("L'assigné doit être membre du projet.")
        return value

    def validate_dependencies(self, tasks):
        project = self.context["view"].project
        if any(t.project_id != project.id for t in tasks):
            raise serializers.ValidationError("Les dépendances doivent appartenir au même projet.")
        if self.instance is not None and planning.would_cycle(self.instance, tasks):
            raise serializers.ValidationError("Cette dépendance créerait une boucle.")
        return tasks

    def validate(self, attrs):
        inst = self.instance
        start = attrs.get("start_date", inst.start_date if inst else None)
        due = attrs.get("due_date", inst.due_date if inst else None)
        if start and due and start > due:
            raise serializers.ValidationError({"start_date": "Le début doit précéder la fin."})
        return attrs


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(source="author.username", read_only=True, default="Utilisateur supprimé")

    class Meta:
        model = Comment
        fields = ["id", "task", "author", "author_name", "content", "created_at"]
        read_only_fields = ["task", "author", "created_at"]
