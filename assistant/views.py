from django.shortcuts import render
from django.http import JsonResponse
from .models import Memory, Conversation
import requests
import os


def chat_page(request):
    conversations = Conversation.objects.all().order_by('-created_at')
    return render(request, 'chat.html', {"conversations": conversations})


def chat_api(request):
    user_message = request.GET.get('message')
    conv_id = request.GET.get('conv_id')

    if not conv_id:
        conversation = Conversation.objects.create()
    else:
        conversation = Conversation.objects.get(id=conv_id)

    past_chats = Memory.objects.filter(conversation=conversation).order_by('created_at')

    messages = [
        {"role": "system", "content": "You are a helpful life assistant."}
    ]

    for chat in past_chats:
        messages.append({"role": "user", "content": chat.message})
        messages.append({"role": "assistant", "content": chat.response})

    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": messages
            }
        )

        reply = response.json()['choices'][0]['message']['content']

    except Exception as e:
        reply = "Error connecting to AI"

    Memory.objects.create(
        conversation=conversation,
        message=user_message,
        response=reply
    )

    return JsonResponse({
        "response": reply,
        "conv_id": conversation.id
    })


def load_chat(request):
    conv_id = request.GET.get('conv_id')
    chats = Memory.objects.filter(conversation_id=conv_id)

    data = []
    for chat in chats:
        data.append({
            "message": chat.message,
            "response": chat.response
        })

    return JsonResponse({"chats": data})