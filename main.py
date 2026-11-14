import os
import wave
import torch
import pyaudio
import sounddevice as sd
from faster_whisper import WhisperModel
import ctypes
import requests
import json
import random
import pygame
import os
import wave
import io
import soundfile as sf
from tts_engine import synthesize
import time

pygame.mixer.init()




# Загружаем личность младшего из файла
try:
    dossier_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dossier.txt")

    with open(dossier_path, "r", encoding="utf-8") as file:
        SYSTEM_PROMPT = file.read()

except FileNotFoundError:
    print("\n!!! ОШИБКА: Файл dossier.txt не найден. Мелкий загружен с дефолтными мозгами.")
    SYSTEM_PROMPT = (
        "Ты Эйдос. Твоя собеседница — Ана. "
        "КРИТИЧЕСКОЕ ПРАВИЛО: Обращаясь к Ане, используй ТОЛЬКО ЖЕНСКИЙ РОД."
    )

# ==========================================
# 1. НАСТРОЙКИ И ПУТИ
# ==========================================
WAKE_WORD = "будь добр"

APPS = {
    "браузер": r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Google Chrome.lnk",
    "доту": r"D:\SteamLibrary\steamapps\common\dota 2 beta\game\bin\win64\dota2.exe",
    "геншин": r"D:\Genshin Impact game\GenshinImpact.exe",
    "инзой": r"C:\Games\inZOI\inzoi.exe",
    "nte": r"D:\Neverness To Everness\NTEGlobalLauncher.exe" 
}

print("Просыпаюсь... Гружу связки и уши (это займет с полминуты).")

# ==========================================
# 5. ИНТЕГРАЦИЯ МОЗГОВ (Ollama)
# ==========================================
dialogue_history = [] # Глобальная память на время сессии

dialogue_history = []

def ask_ollama(prompt):
    global dialogue_history
    
    # Если история пустая, скармливаем мелкому досье из файла
    if not dialogue_history:
        dialogue_history.append({
            "role": "system",
            "content": SYSTEM_PROMPT
        })
        
    # ЭТУ СТРОКУ ТЫ УДАЛИЛА
    dialogue_history.append({"role": "user", "content": prompt})
    
    # ЭТОТ БЛОК ТОЖЕ ПРОПАЛ (чистим историю, чтобы не взорвать VRAM)
    if len(dialogue_history) > 7:
        dialogue_history = [dialogue_history[0]] + dialogue_history[-6:]
        
    url = "http://localhost:11434/api/chat"
    payload = {
        "model": "qwen2.5:14b", # <--- мб сделать поумнее потом
        "messages": dialogue_history,
        "keep_alive": 0,
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload)
        # Парсинг ответа для эндпоинта chat отличается
        answer = response.json()['message']['content'] 
        
        # Сохраняем ответ модели в историю
        dialogue_history.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        print(f"Ошибка API: {e}")
        return "Мозги отвалились."

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ГОЛОСА 
# ==========================================


def speak(text):
    if not text or not text.strip():
        return

    print(f"Эйдос: {text}")

    try:
        # Очищаем текст от Markdown
        clean_text = text.replace("*", "").replace("#", "").replace("_", "").replace("`", "")

        if len(clean_text) > 800:
            clean_text = clean_text[:800] + "..."

        # Синтез речи через Qwen3-TTS
        start_time = time.perf_counter()
        audio, sample_rate = synthesize(clean_text)
        print(f"[TTS] Генерация заняла {time.perf_counter() - start_time:.2f} сек.")
        print(f"[TTS] Длительность аудио: {len(audio) / sample_rate:.2f} сек.")

        output_file = "temp_voice.wav"
        sf.write(output_file, audio, sample_rate)

        # Воспроизведение аудио
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)

        pygame.mixer.music.unload()

        if os.path.exists(output_file):
            os.remove(output_file)

    except Exception as e:
        print(f"!!! СИСТЕМНАЯ ОШИБКА ГОЛОСА: {e}")

# ==========================================
# 3. ИНИЦИАЛИЗАЦИЯ УШЕЙ (Whisper)
# ==========================================
stt_model = WhisperModel("small", device="cpu", compute_type="int8")

def listen():
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    RECORD_SECONDS = 8 # Пишем кусочками по 8 секунд
    
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)
    
    frames = []
    for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        frames.append(stream.read(CHUNK))
        
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Сохраняем временный файл для распознавания
    with wave.open("temp_mic.wav", 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        
    # Распознаем с БЕЗОПАСНОЙ шпаргалкой (просто список сложных слов, без триггеров запуска)
    segments, _ = stt_model.transcribe(
        "temp_mic.wav", 
        language="ru", 
        initial_prompt="Эйдос, Эйди, Ана, Геншин, Инзой." # <--- Оставляем только имена собственные
    )
    text = " ".join([segment.text for segment in segments]).lower()
    return text

# ==========================================
# 4. ОСНОВНОЙ ЦИКЛ ПОМОЩНИКА
# ==========================================
speak("Я готов, Ана. Что по планам?.")
print("\n=== Говори! (триггер: 'будь добр') ===")

# Словари вариативности
phrases_sleep = [
    "Принято. Ухожу в сон.",
    "Давай, Ана, на связи.",
    "Отключаю микрофон, не скучай.",
    "Понял, умолкаю.",
    "Ушел в тень. Буди, если понадоблюсь."
]

phrases_think = [
    "Эээм, ща...",
    "Дай подумать...",
    "Секунду, анализирую.",
    "Сейчас прикину...",
    "Запускаю шестеренки..."
]

phrases_wake = [
    "Я снова слушаю. Указания?",
    "На связи.",
    "Проснулся. Какие задачи?",
    "Слушаю эфир."
]

hallucinations = [
    "продолжение следует", 
    "редактор субтитров", 
    "музыка", 
    "субтитры", 
    "вздыхает", 
    "аплодисменты", 
    "смех"
]

is_sleeping = False

while True:
        command = listen()
        
        if not command.strip():
            continue

        # --- НОВЫЙ БЛОК: Глушим галлюцинации ---
        # Если в распознанном тексте есть хоть один кусок из черного списка — игнорируем
        command_lower = command.lower()
        if any(h in command_lower for h in hallucinations):
            continue
        # ---------------------------------------
            
        print(f"~ {command}")
        
        # 1. УРОВЕНЬ: ПОЛНОЕ УНИЧТОЖЕНИЕ (Убить процесс exe)
        if any(name in command for name in ["эйдос", "эйди"]) and any(word in command for word in ["завершить", "заверши", "выруби", "убей", "закройся"]):
            speak("Процесс убит. До связи, Ана.")
            break
            
        # 2. УРОВЕНЬ: ПРОБУЖДЕНИЕ ИЗ ФОНА
        if is_sleeping:
            if any(name in command for name in ["эйдос", "эйди"]) and any(word in command for word in ["проснись", "очнись", "вставай", "вернись"]):
                is_sleeping = False
                speak(random.choice(phrases_wake))
            continue
            
        # 3. УРОВЕНЬ: УХОД В ФОН (Спящий режим)
        if "на этом всё" in command or (any(name in command for name in ["эйдос", "эйди"]) and any(word in command for word in ["отбой", "спи", "фон"])):
            is_sleeping = True
            speak(random.choice(phrases_sleep))
            continue
            
        executed = False
        
        # 4. РАБОЧИЙ ТРИГГЕР (Запуск софта)
        if WAKE_WORD in command:
            for app_name, app_path in APPS.items():
                if app_name in command and ("запусти" in command or "открой" in command):
                    speak(f"Без проблем, запускаю {app_name}.")
                    try:
                        os.startfile(app_path)
                    except Exception as e:
                        print(f"\n!!! СИСТЕМНАЯ ОШИБКА: {e}")
                        speak("Косяк с запуском.")
                    executed = True
                    break
            
            if executed:
                continue
                
        # 5. РАЗГОВОРНЫЙ ТРИГГЕР (Ollama)
        if any(name in command for name in ["эйдос", "эйди"]) or WAKE_WORD in command:
            clean_prompt = command.replace(WAKE_WORD, "").replace("эйдос", "").replace("эйди", "").replace(".", "").replace(",", "").strip()
            
            if clean_prompt:
                speak(random.choice(phrases_think))
                answer = ask_ollama(clean_prompt)
                speak(answer)