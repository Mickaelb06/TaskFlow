from rest_framework import serializers

from accounts.models import Profile
from accounts.timezones import zone
from projects.models import Project

from . import services
from .models import Event


class EventSerializer(serializers.ModelSerializer):
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), allow_null=True, required=False)
    project_name = serializers.CharField(source="project.name", read_only=True, default=None)
    creator_name = serializers.CharField(source="creator.username", read_only=True, default=None)
    can_edit = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = ["id", "project", "project_name", "title", "description", "starts_at", "ends_at", "timezone",
                  "creator", "creator_name", "can_edit"]
        read_only_fields = ["creator"]

    def get_can_edit(self, obj):
        return services.can_edit(self.context["request"].user, obj)

    def to_internal_value(self, data):
        """Une date-heure sans décalage (« 2026-10-12T14:00 ») est l'heure murale du fuseau `timezone`
        (à défaut, celui de l'utilisateur) ; on la convertit avant la validation DRF, qui la lirait sinon
        dans le fuseau du serveur."""
        user = self.context["request"].user
        data = data.copy() if hasattr(data, "copy") else dict(data)
        name = data.get("timezone") or (self.instance.timezone if self.instance else "") or Profile.for_user(user).timezone
        tz = zone(name)
        for key in ("starts_at", "ends_at"):
            if isinstance(data.get(key), str):
                try:
                    data[key] = services.to_aware(data[key], tz).isoformat()
                except Exception:
                    raise serializers.ValidationError({key: "Date-heure invalide."})
        return super().to_internal_value(data)

    def validate_timezone(self, value):
        if value:
            zone(value)
        return value

    def validate_project(self, project):
        if project is not None and not Project.objects.filter(pk=project.pk, membership__user=self.context["request"].user).exists():
            raise serializers.ValidationError("Projet introuvable.")
        return project


class CalendarTaskSerializer(serializers.Serializer):
    """Tâche vue du calendrier : posée à la journée, sans heure."""

    id = serializers.IntegerField()
    project = serializers.IntegerField(source="project_id")
    project_name = serializers.CharField(source="project.name")
    title = serializers.CharField()
    status = serializers.CharField()
    priority = serializers.IntegerField()
    start_date = serializers.DateField()
    due_date = serializers.DateField()
    is_milestone = serializers.BooleanField()
    assignee_name = serializers.CharField(source="assignee.username", default=None)
