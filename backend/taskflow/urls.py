from django.http import JsonResponse
from django.urls import include, path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


def health(_request):
    from tasks import planning_engine

    return JsonResponse({"status": "ok", "planning_engine": planning_engine.NAME})


urlpatterns = [
    path("health/", health),
    path("api/auth/token/", TokenObtainPairView.as_view()),
    path("api/auth/refresh/", TokenRefreshView.as_view()),
    path("api/", include("accounts.urls")),
    path("api/", include("projects.urls")),
    path("api/", include("tasks.urls")),
    path("api/", include("agenda.urls")),
    path("api/", include("chat.urls")),
]
