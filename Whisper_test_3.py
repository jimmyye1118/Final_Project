import sounddevice as sd
import numpy as np
import whisper
import tempfile
import wave
import pyttsx3
from sentence_transformers import SentenceTransformer, util
import threading
# import keyboard  # 需要安裝：pip install keyboard

# 初始化模型
whisper_model = whisper.load_model("base")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
tts_engine = pyttsx3.init()

# 關鍵字與動作
keyword_actions = {
    "開始": lambda: print("開始任務"),
    "暫停": lambda: print("暫停"),
    "紅色": lambda: print("紅色"),
    "藍色": lambda: print("藍色"),
    "黃色": lambda: print("黃色"),
    "綠色": lambda: print("綠色"),
}

# 預先建立語意向量
keyword_list = list(keyword_actions.keys())
keyword_embeddings = embedding_model.encode(keyword_list, convert_to_tensor=True)

recording_data = []
is_recording = False
fs = 16000  # 取樣率

def audio_callback(indata, frames, time, status):
    if is_recording:
        recording_data.append(indata.copy())

def record_audio():
    global recording_data
    recording_data = []
    print("開始錄音...")
    with sd.InputStream(samplerate=fs, channels=1, dtype='int16', callback=audio_callback):
        while is_recording:
            sd.sleep(100)
    print("錄音結束")

def speak(text):
    print(f"TTS 說話：{text}")
    tts_engine.say(text)
    tts_engine.runAndWait()

def save_audio_to_file():
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        with wave.open(f.name, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(fs)
            audio_data = np.concatenate(recording_data, axis=0)
            wf.writeframes(audio_data.tobytes())
        return f.name

def process_command(audio_path):
    result = whisper_model.transcribe(audio_path, language="zh")
    text = result['text'].strip()
    print(f"辨識結果：{text}")

    user_embedding = embedding_model.encode(text, convert_to_tensor=True)
    cosine_scores = util.cos_sim(user_embedding, keyword_embeddings)
    best_idx = cosine_scores.argmax()
    best_score = cosine_scores[0][best_idx].item()
    best_keyword = keyword_list[best_idx]

    print(f"🔍 最相似：{best_keyword}（分數：{best_score:.2f}）")

    if best_score >= 0.6:
        keyword_actions[best_keyword]()
    else:
        speak("請再說一次")

def main_loop():
    global is_recording
    print("按下 g 開始錄音，s 停止錄音並辨識，q 離開：")
    while True:
        key = input()

        if key == "g" and not is_recording:
            is_recording = True
            threading.Thread(target=record_audio).start()

        elif key == "s" and is_recording:
            is_recording = False
            audio_file = save_audio_to_file()
            process_command(audio_file)

        elif key == "q":
            print("已退出程式")
            break

        else:
            print("無效指令，請重新輸入")

main_loop()