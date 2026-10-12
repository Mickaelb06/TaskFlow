from django.urls import path

from . import views

urlpatterns = [
    path("chat/conversations/", views.ConversationListView.as_view()),
    path("chat/direct/", views.DirectView.as_view()),
    path("chat/contacts/", views.ContactsView.as_view()),
    path("chat/conversations/<int:pk>/messages/", views.MessagesView.as_view()),
    path("chat/conversations/<int:pk>/read/", views.ReadView.as_view()),
    path("chat/messages/<int:pk>/", views.MessageDetailView.as_view()),
    path("chat/messages/<int:pk>/reactions/", views.ReactionView.as_view()),
    path("chat/attachments/<int:pk>/", views.AttachmentView.as_view()),
    path("chat/search/", views.SearchView.as_view()),
    path("chat/summary/", views.SummaryView.as_view()),
    path("notifications/", views.NotificationsView.as_view()),
]
