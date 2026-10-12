from django.urls import path

from .views import CalendarView, ContactsView, EventViewSet, RsvpView, SkipView

urlpatterns = [
    path("calendar/", CalendarView.as_view()),
    path("events/", EventViewSet.as_view({"get": "list", "post": "create"})),
    path("events/<int:pk>/", EventViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})),
    path("events/<int:pk>/rsvp/", RsvpView.as_view()),
    path("events/<int:pk>/skip/", SkipView.as_view()),
    path("calendar/contacts/", ContactsView.as_view()),
]
