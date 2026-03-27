from django.db import models

class Document(models.Model):
    file = models.FileField(upload_to='pdfs/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class Note(models.Model):
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class Chat(models.Model):
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)