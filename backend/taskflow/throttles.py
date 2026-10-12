from rest_framework.permissions import SAFE_METHODS
from rest_framework.throttling import ScopedRateThrottle


class WritesOnlyThrottle(ScopedRateThrottle):
    """Limite de débit réservée aux écritures : la lecture (relève de la messagerie toutes les 15 s) n'est jamais freinée."""

    def allow_request(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return super().allow_request(request, view)
