from django.urls import path
from . import views

urlpatterns = [
    path('', views.upload_pdf, name='upload_pdf'),
    path('chat-api/', views.chat_api, name='chat_api'),
]