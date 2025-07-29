import os
from pygame import mixer

class AudioController:
    def __init__(self):
        # 獲取專案根目錄路徑
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.music_dir = os.path.join(self.project_root, 'music')
        print(f"音效資料夾路徑: {self.music_dir}")
    
    def speak(self, file_name):
        """播放音效檔案"""
        try:
            mixer.init()
            audio_file = os.path.join(self.music_dir, str(file_name) + '.mp3')
            print(f"嘗試播放音效: {audio_file}")
            
            # 檢查檔案是否存在
            if not os.path.exists(audio_file):
                print(f"警告: 音效檔案不存在 - {audio_file}")
                return
                
            mixer.music.load(audio_file)
            mixer.music.play()
            print(f"成功播放音效: {file_name}")
            
        except Exception as e:
            print(f"播放音效失敗: {e}")
            print(f"檔案路徑: {audio_file}")