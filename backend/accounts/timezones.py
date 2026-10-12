from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError


def zone(name):
    """ZoneInfo pour un nom IANA (« Europe/Paris »), ValidationError sinon."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValidationError(f"Fuseau horaire inconnu : « {name} ».")
