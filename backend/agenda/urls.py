from django.urls import path

from .views import CalendarView, EventViewSet

urlpatterns = [
    path("calendar/", CalendarView.as_view()),
    path("events/", EventViewSet.as_view({"get": "list", "post": "create"})),
    path("events/<int:pk>/", EventViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})),
]
