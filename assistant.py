import speech_recognition as sr
import pyttsx3
import requests
import os
import webbrowser
import datetime
import signal
import sys
from dotenv import load_dotenv

# LOAD ENV
load_dotenv()

# VOICE
engine = pyttsx3.init()
engine.setProperty('rate', 170)

# MEMORY
conversation_history = []

# INTERRUPT FLAG
interrupted = False

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    global interrupted
    print("\n\n⚠️ Interrupt received! Stopping...")
    interrupted = True
    try:
        engine.stop()
    except:
        pass
    speak("Goodbye!")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# SPEAK
def speak(text):
    print("AI:", text)
    engine.say(text)
    engine.runAndWait()

# LISTEN
def listen():
    with sr.Microphone() as source:
        print("Listening...")
        recognizer.adjust_for_ambient_noise(source)
        audio = recognizer.listen(source)

    try:
        text = recognizer.recognize_google(audio)
        print("You:", text)
        return text.lower()
    except:
        return ""

# INIT MIC
recognizer = sr.Recognizer()

# AI
def ask_ai(message):

    global conversation_history

    conversation_history.append({"role": "user", "content": message})

    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."}
        ] + conversation_history
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
        )

        reply = response.json()['choices'][0]['message']['content']

        conversation_history.append({"role": "assistant", "content": reply})

        return reply

    except:
        return "Error connecting to AI"

# COMMANDS
def handle_command(command):
    global interrupted

    # Check for stop/interrupt command
    if any(word in command.lower() for word in ['stop', 'quit', 'exit', 'cancel', 'interrupt', 'shut up', 'stop listening']):
        speak("Stopped! 🛑")
        return

    if "time" in command:
        time = datetime.datetime.now().strftime("%I:%M %p")
        speak(f"The time is {time}")

    elif "youtube" in command:
        # Extract search query if present
        if "search" in command or "play" in command or "watch" in command:
            # Remove youtube keyword and extract query
            query = command.replace("youtube", "").replace("search", "").replace("play", "").replace("watch", "").strip()
            if query:
                search_query = query.replace(" ", "+")
                url = f"https://www.youtube.com/results?search_query={search_query}"
                speak(f"Searching YouTube for {query}")
                webbrowser.open(url)
            else:
                speak("Opening YouTube")
                webbrowser.open("https://youtube.com")
        else:
            speak("Opening YouTube")
            webbrowser.open("https://youtube.com")

    elif "google" in command:
        speak("Opening Google")
        webbrowser.open("https://google.com")

    elif "exit" in command:
        speak("Goodbye")
        exit()

    else:
        response = ask_ai(command)
        speak(response)

# MAIN
def main():
    global interrupted
    speak("Hello, I am your assistant. Press Ctrl+C to stop.")

    while not interrupted:
        try:
            command = listen()

            if command:
                handle_command(command)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
            continue

    speak("Goodbye!")

# RUN
if __name__ == "__main__":
    main()