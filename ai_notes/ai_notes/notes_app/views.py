from django.shortcuts import render
from django.conf import settings
import os

from .models import Document, Note, Chat
from .utils import extract_text, generate_notes_with_rag, chat_with_pdf


def upload_pdf(request):

    # =========================
    # 🟢 HANDLE POST REQUEST
    # =========================
    if request.method == 'POST':

        # =========================
        # 📂 CASE 1: UPLOAD BUTTON
        # =========================
        if 'upload_btn' in request.POST:

            files = request.FILES.getlist('pdfs')

            if not files:
                return render(request, 'result.html', {
                    'error': 'Please select PDF files'
                })

            combined_text = ""

            # Ensure media folder exists
            os.makedirs(settings.MEDIA_ROOT, exist_ok=True)

            # Optional: clear old data
            Document.objects.all().delete()
            Note.objects.all().delete()
            Chat.objects.all().delete()

            for pdf in files:
                try:
                    filename = pdf.name.replace(" ", "_")
                    file_path = os.path.join(settings.MEDIA_ROOT, filename)

                    # Save file
                    with open(file_path, 'wb+') as f:
                        for chunk in pdf.chunks():
                            f.write(chunk)

                    # Save in DB
                    Document.objects.create(file=pdf)

                    print("Saved:", file_path)

                    # Extract text
                    text = extract_text(file_path)
                    if text:
                        combined_text += text + "\n"

                except Exception as e:
                    print("Error:", str(e))

            if not combined_text.strip():
                return render(request, 'result.html', {
                    'error': 'No readable text found'
                })

            # Generate notes
            notes = generate_notes_with_rag(combined_text)

            # Save notes
            Note.objects.create(content=notes)

            return render(request, 'result.html', {
                'notes': notes,
                'chat_history': []
            })

        # =========================
        # 💬 CASE 2: CHAT BUTTON
        # =========================
        elif 'chat_btn' in request.POST:

            user_query = request.POST.get('query')

            if not user_query or user_query.strip() == "":
                note = Note.objects.last()
                chats = Chat.objects.all()

                return render(request, 'result.html', {
                    'notes': note.content if note else "",
                    'chat_history': chats,
                    'error': 'Please enter a message'
                })

            # Get all documents
            documents = Document.objects.all()

            if not documents:
                return render(request, 'result.html', {
                    'error': 'Please upload PDFs first'
                })

            combined_text = ""

            for doc in documents:
                try:
                    file_path = doc.file.path
                    text = extract_text(file_path)
                    if text:
                        combined_text += text + "\n"
                except Exception as e:
                    print("Error reading file:", str(e))

            # Generate answer
            answer = chat_with_pdf(combined_text, user_query)

            # Save chat
            Chat.objects.create(
                question=user_query,
                answer=answer
            )

            chats = Chat.objects.all()
            note = Note.objects.last()

            return render(request, 'result.html', {
                'notes': note.content if note else "",
                'chat_history': chats
            })

    # =========================
    # 🟢 HANDLE GET REQUEST
    # =========================
    note = Note.objects.last()
    chats = Chat.objects.all()

    return render(request, 'result.html', {
        'notes': note.content if note else "Upload PDFs to generate notes",
        'chat_history': chats
    })


from django.http import JsonResponse

def chat_api(request):
    if request.method == "POST":
        query = request.POST.get("query")

        if not query:
            return JsonResponse({"error": "Empty query"})

        # Get documents
        documents = Document.objects.all()

        combined_text = ""
        for doc in documents:
            text = extract_text(doc.file.path)
            if text:
                combined_text += text

        # Get AI response
        answer = chat_with_pdf(combined_text, query)

        # Save chat
        Chat.objects.create(question=query, answer=answer)

        return JsonResponse({
            "question": query,
            "answer": answer
        })