# config.py

import DobotDllType as dType
import numpy as np
import os

# --- 視覺系統設定 ---
VIDEO_SOURCE = 1  # 攝影機來源，0 通常為內建攝影機，1+ 為外部攝影機
GAMMA_VALUE = 0.6  # 亮度調整參數 (0.1 較暗 --- 0.9 較亮)
MODEL_PATH = "./Cube_Color_4_and_Defect_Model/V12_4_Color_Training12/weights/best.pt" # YOLO 模型路徑
MASK_IMAGE_PATH = "mask.png"  # 影像遮罩圖片路徑 (應與 main.py 在同目錄或指定完整路徑)
CONFIDENCE_THRESHOLD = 0.7  # 物件辨識的置信度閾值
MIN_CONTOUR_AREA = 500  # 最小輪廓面積，用於過濾雜訊或小型異物
BOUNDING_BOX_PADDING = 20 # 邊界框填充，用於判斷未知物件是否與已知物件重疊

# --- Dobot 機械手臂設定 ---
DOBOT_PORT = "COM4"  # Dobot 連接埠
DOBOT_BAUDRATE = 115200 # Dobot 鮑率

# 吸盤中心點校準參數 (這些值需要根據您的實際校準結果進行精確調整)
X_CENTER_OFFSET_VISION = 310
Y_CENTER_OFFSET_VISION = 285

# Dobot 機械手臂動作座標 (請根據您的實驗台實際情況調整)
HOME_POS = {'x': 270, 'y': 0, 'z': 50, 'r': 0} # Dobot 的預設歸位點
PICK_Z = 8  # 夾取物件時的 Z 軸高度 (靠近物件表面)
DROP_Z = 40 # 放置物件時的 Z 軸高度 (釋放吸盤後)
HOVER_Z = 70 # 在夾取或放置前/後的懸停 Z 軸高度

# 各種顏色物件的放置座標
DROP_OFF_COORDINATES = {
    "yellow": {'x': 10, 'y': 213},
    "blue": {'x': 150, 'y': 213},
    "red": {'x': 80, 'y': 213},
    "green": {'x': 220, 'y': 213},
}

# Dobot 連接狀態的映射
DOBOT_CONNECT_STR = {
    dType.DobotConnect.DobotConnect_NoError: "DobotConnect_NoError",
    dType.DobotConnect.DobotConnect_NotFound: "DobotConnect_NotFound",
    dType.DobotConnect.DobotConnect_Occupied: "DobotConnect_Occupied"
}

# --- 物件顏色映射 (用於影像顯示) ---
COLOR_MAP = {
    'red': (0, 0, 255),       # 紅色 (BGR 格式)
    'blue': (255, 0, 0),      # 藍色
    'green': (0, 255, 0),     # 綠色
    'yellow': (0, 255, 255),  # 黃色
    'broken': (141, 23, 232), # 損毀 (紫紅色)
    'unknown': (255, 255, 255) # 未知 (白色)
}

# --- 音效設定 ---
MUSIC_PATH = './music/' # 音效檔案目錄

# --- 網路通訊 (Socket.IO) 設定 ---
PYTHON_SOCKET_IO_PORT = 5000 # Python Flask-SocketIO 伺服器監聽的埠
PYTHON_SOCKET_IO_HOST = '0.0.0.0' # Python 伺服器監聽的 IP (0.0.0.0 表示監聽所有可用介面)

NODEJS_WEB_SERVER_PORT = 3000 # Node.js 網頁伺服器監聽的埠

# --- 其他設定 ---
KERNEL_SIZE = (5, 5) # 形態學操作的核大小