from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Profile
from .timezones import zone

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "password"]
        extra_kwargs = {"email": {"required": True}}

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Le compte + ses préférences (fuseaux horaires, modifiables via PATCH /me/)."""

    timezone = serializers.CharField(source="profile.timezone", required=False, max_length=64)
    secondary_timezone = serializers.CharField(source="profile.secondary_timezone", required=False, allow_blank=True, max_length=64)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "is_superuser", "timezone", "secondary_timezone"]
        read_only_fields = ["username", "email", "is_staff", "is_superuser"]

    def validate_timezone(self, value):
        zone(value)
        return value

    def validate_secondary_timezone(self, value):
        if value:
            zone(value)
        return value

    def update(self, instance, validated_data):
        prefs = validated_data.get("profile", {})
        profile = instance.profile  # la même instance que celle relue pour la réponse
        for key, value in prefs.items():
            setattr(profile, key, value)
        profile.save()
        return instance
