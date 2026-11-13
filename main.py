import os
import wave
import torch
import pyaudio
import subprocess
import sounddevice as sd
from faster_whisper import WhisperModel
import ctypes
import requests
import json
import random
import edge_tts
import asyncio
import pygame
import os
import subprocess

pygame.mixer.init()

# --- ВОССТАНАВЛИВАЕМ ГОЛОСОВЫЕ СВЯЗКИ SILERO ---
print("Гружу резервные связки (Silero)...")
device = torch.device('cpu')
torch.set_num_threads(4)

# Загружаем модель в глобальную переменную model
try:
    model, example_text = torch.hub.load(repo_or_dir='snakers4/silero-models',
                                         model='silero_tts',
                                         language='ru',
                                         speaker='v3_1_ru')
    model.to(device)
except Exception as e:
    print(f"!!! ОШИБКА ЗАГРУЗКИ SILERO: {e}")
# ----------------------------------------------

# Загружаем личность младшего из файла
try:
    with open("dossier.txt", "r", encoding="utf-8") as file:
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
        
    # Добавляем твой запрос
    dialogue_history.append({"role": "user", "content": prompt})
    
    # Ограничиваем историю (системный промпт + последние 6 сообщений), чтобы не переполнять VRAM
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
# 2. ИНИЦИАЛИЗАЦИЯ ГОЛОСА (Silero)
# ==========================================
device = torch.device('cpu')
tts_model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models',
                              model='silero_tts',
                              language='ru',
                              speaker='v4_ru')

def speak(text):
    print(f"Эйдос: {text}")
    
    voice = "ru-RU-DmitryNeural" 
    output_file = "temp_voice.mp3"
    
    try:
        # Питон сам незаметно вбивает ту самую команду в консоль
        subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", output_file], check=True)
        
        # Воспроизводим скачанный файл
        pygame.mixer.music.load(output_file)
        pygame.mixer.music.play()
        
        # Ждем, пока мелкий договорит
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
            
        # Отпускаем файл и удаляем, чтобы не плодить мусор
        pygame.mixer.music.unload()
        if os.path.exists(output_file):
            os.remove(output_file)
            
    except Exception as e:
        print(f"\n!!! ОБЛАКО ЛЕЖИТ. Подрубаю резервный голос. Ошибка: {e}")
        
        # --- ТВОЙ ЗАПАСНОЙ ПАРАШЮТ (Silero) ---
        try:
            audio = model.apply_tts(text=text,
                                    speaker='eugene',
                                    sample_rate=48000)
            import sounddevice as sd
            sd.play(audio, 48000)
            sd.wait()
        except Exception as silero_error:
            print(f"Даже локальный голос отвалился: {silero_error}")

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
        
    # Распознаем с нашей шпаргалкой
    segments, _ = stt_model.transcribe(
        "temp_mic.wav", 
        language="ru", 
        initial_prompt="Эйдос, будь добр, запусти Геншин, инзой, nte. Отбой, отключись."
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
        if "эйдос" in command and any(word in command for word in ["завершить", "заверши", "выруби", "убей", "закройся"]):
            speak("Процесс убит. До связи, Ана.")
            break
            
        # 2. УРОВЕНЬ: ПРОБУЖДЕНИЕ ИЗ ФОНА
        if is_sleeping:
            if "эйдос" in command and any(word in command for word in ["проснись", "очнись", "вставай", "вернись"]):
                is_sleeping = False
                speak(random.choice(phrases_wake)) # <--- РАНДОМНАЯ ФРАЗА ПРОБУЖДЕНИЯ
            continue 
            
        # 3. УРОВЕНЬ: УХОД В ФОН (Спящий режим)
        if "на этом всё" in command or ("эйдос" in command and any(word in command for word in ["отбой", "спи", "фон"])):
            is_sleeping = True
            speak(random.choice(phrases_sleep)) # <--- РАНДОМНАЯ ФРАЗА УХОДА В СОН
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
        if "эйдос" in command or WAKE_WORD in command:
            clean_prompt = command.replace(WAKE_WORD, "").replace("эйдос", "").replace(".", "").replace(",", "").strip()
            
            if clean_prompt:
                speak(random.choice(phrases_think)) # <--- РАНДОМНАЯ ФРАЗА РАЗДУМЬЯ
                answer = ask_ollama(clean_prompt)
                speak(answer)