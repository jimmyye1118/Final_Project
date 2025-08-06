import sounddevice as sd
import numpy as np
import tempfile
import wave
import pyttsx3
from sentence_transformers import SentenceTransformer, util
from faster_whisper import WhisperModel
import threading

class VoiceRecognizer:
    def __init__(self):
        """初始化語音辨識與語音合成模型"""
        print("正在載入語音辨識與語意模型...")
        # 初始化語音辨識模型（使用 CPU）
        self.whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        # 初始化語意比較與語音合成模型
        self.embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.tts_engine = pyttsx3.init()
        
        # 關鍵字與動作
        self.keyword_actions = {
            "開始": lambda: "start",
            "暫停": lambda: "stop",
            "紅色": lambda: "red",
            "藍色": lambda: "blue",
            "黃色": lambda: "yellow",
            "綠色": lambda: "green",
        }
        
        # 預先建立語意向量
        self.keyword_list = list(self.keyword_actions.keys())
        self.keyword_embeddings = self.embedding_model.encode(self.keyword_list, convert_to_tensor=True)
        
        self.recording_data = []
        self.is_recording = False
        self.fs = 16000  # 取樣率
        self.lock = threading.Lock()
        print("語音模組載入完成。")

    def _audio_callback(self, indata, frames, time, status):
        """錄音的回調函數"""
        if self.is_recording:
            self.recording_data.append(indata.copy())

    def start_recording(self):
        """啟動錄音"""
        with self.lock:
            if self.is_recording:
                print("錄音已在進行中。")
                return
            self.is_recording = True
            self.recording_data = []
            print("🎙️ 開始錄音...")
            self.stream = sd.InputStream(
                samplerate=self.fs, 
                channels=1, 
                dtype='int16', 
                callback=self._audio_callback
            )
            self.stream.start()

    def stop_recording(self):
        """停止錄音並回傳辨識結果與語音內容"""
        with self.lock:
            if not self.is_recording:
                print("錄音未在進行中。")
                return None, None

            self.is_recording = False
            self.stream.stop()
            self.stream.close()

        print("🛑 錄音結束，正在辨識...")

        audio_file_path = self._save_audio_to_file()
        if audio_file_path:
            command, text = self._process_command(audio_file_path)
            return command, text
        return None, None


    def _save_audio_to_file(self):
        """將錄音資料儲存為暫存 WAV 檔案"""
        if not self.recording_data:
            print("沒有錄音資料。")
            return None
        
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            with wave.open(f.name, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.fs)
                audio_data = np.concatenate(self.recording_data, axis=0)
                wf.writeframes(audio_data.tobytes())
            return f.name

    def _process_command(self, audio_path):
        """處理語音指令，進行辨識與語意比對，回傳 (command, text)"""
        segments, _ = self.whisper_model.transcribe(audio_path, beam_size=5, language="zh")
        text = ''.join([segment.text for segment in segments]).strip()
        print(f"📝 辨識結果：{text}")
        
        if not text:
            self.speak("沒有聽清楚，請再說一次。")
            return None, text  # 即 return (None, "")
            
        user_embedding = self.embedding_model.encode(text, convert_to_tensor=True)
        cosine_scores = util.cos_sim(user_embedding, self.keyword_embeddings)
        best_idx = cosine_scores.argmax()
        best_score = cosine_scores[0][best_idx].item()
        best_keyword = self.keyword_list[best_idx]
        
        print(f"🔍 最相似：{best_keyword}（分數：{best_score:.2f}）")
        
        if best_score >= 0.6:
            return self.keyword_actions[best_keyword](), text  # 回傳指令與辨識結果文字
        else:
            self.speak("無法理解您的指令，請再說一次。")
            return None, text


    def speak(self, text):
        """語音合成功能"""
        print(f"TTS 說話：{text}")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

# 測試用，您可以獨立執行此檔案來測試語音模組
if __name__ == '__main__':
    vr = VoiceRecognizer()
    
    print("📢 按下 'g' 開始錄音，'s' 停止並辨識，'q' 退出")
    while True:
        key = input("➡️ 輸入指令：")
        if key == "g":
            vr.start_recording()
        elif key == "s":
            command = vr.stop_recording()
            if command:
                print(f"執行指令：{command}")
        elif key == "q":
            print("👋 退出測試")
            break
        else:
            print("⚠️ 無效指令，請輸入 g, s 或 q")