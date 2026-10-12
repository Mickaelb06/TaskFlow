from rest_framework import serializers

from .models import Membership, Project
from .services import get_role


class ProjectSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "name", "description", "deadline", "skip_weekends", "owner", "role", "created_at"]
        read_only_fields = ["owner", "created_at"]

    def get_role(self, obj):
        return get_role(self.context["request"].user, obj)


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Membership
        fields = ["user_id", "username", "role"]


class AddMemberSerializer(serializers.Serializer):
    identifier = serializers.CharField(help_text="Nom d'utilisateur ou email")
    role = serializers.ChoiceField(choices=Membership.Role.choices, default=Membership.Role.MEMBER)


class RoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Membership.Role.choices)
