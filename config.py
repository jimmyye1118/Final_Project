import numpy as np

# 吸盤中心點調整
X_Center = 321
Y_Center = 255

# 影像編號
Video_num = 1  # 修改為 0，測試是否正確
# 亮度調整參數 0.1(暗)---0.9(亮)
Gamma_Value = 0.6

# 不動參數
n1 = 0
color_th = 1500
kernel = np.ones((5, 5), np.uint8)

# 顏色映射
color_map = {
    'red': (0, 0, 255),      # 紅色
    'blue': (255, 0, 0),     # 藍色
    'green': (0, 255, 0),    # 綠色
    'yellow': (0, 255, 255), # 黃色
    'broken': (141, 23, 232)     # 損毀
}

# 物件計數初始化
object_counts_init = {
    'red': 0,
    'blue': 0,
    'yellow': 0,
    'green': 0,
    'broken': 0,
    'unknown': 0
}

# Dobot 連接參數
DOBOT_PORT = "COM3"
DOBOT_BAUDRATE = 115200