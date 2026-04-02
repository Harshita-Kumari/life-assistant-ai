from django.urls import path
from .views import chat_page, chat_api, load_chat

urlpatterns = [
    path('', chat_page),
    path('chat-api/', chat_api),
    path('load-chat/', load_chat),
]