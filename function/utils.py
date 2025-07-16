# utils.py

import cv2
import numpy as np
from pygame import mixer
import os
from config import MUSIC_PATH

def speak(file_name):
    """
    播放指定名稱的 MP3 音效檔。
    音效檔應位於 config.MUSIC_PATH 指定的目錄下。
    """
    try:
        if not mixer.get_init(): # 檢查 mixer 是否已初始化
            mixer.init()
        sound_file = os.path.join(MUSIC_PATH, f'{file_name}.mp3')
        if os.path.exists(sound_file):
            mixer.music.load(sound_file)
            mixer.music.play()
        else:
            print(f"錯誤：找不到音效檔案 '{sound_file}'。")
    except Exception as e:
        print(f"播放音效 '{file_name}' 時發生錯誤: {e}")

def adjust_gamma(image, gamma=1.0):
    """
    調整影像的 Gamma 值以改變亮度。
    gamma 值小於 1 會使影像變亮，大於 1 會使影像變暗。
    """
    invGamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    return cv2.LUT(image, table)