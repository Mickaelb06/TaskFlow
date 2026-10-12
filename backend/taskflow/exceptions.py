from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions
from rest_framework.views import exception_handler


def handler(exc, context):
    """Convertit les ValidationError de la couche service en réponse 400."""
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.messages)
    return exception_handler(exc, context)
