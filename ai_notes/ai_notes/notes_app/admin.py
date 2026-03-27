from django.contrib import admin
from .models import Document, Note, Chat

admin.site.register(Document)
admin.site.register(Note)
admin.site.register(Chat)