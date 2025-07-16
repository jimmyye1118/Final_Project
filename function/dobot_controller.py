# dobot_controller.py

import DobotDllType as dType
import time
from config import DOBOT_PORT, DOBOT_BAUDRATE, DOBOT_CONNECT_STR, HOME_POS, PICK_Z, DROP_Z, HOVER_Z, X_CENTER_OFFSET_VISION, Y_CENTER_OFFSET_VISION, DROP_OFF_COORDINATES

class DobotController:
    """
    管理與 Dobot 機械手臂的連線和操作。
    """
    def __init__(self):
        self.api = None
        self.is_connected = False
        self.connect_status = dType.DobotConnect.DobotConnect_NotFound

    def connect(self):
        """
        嘗試連接 Dobot 機械手臂並初始化參數。
        返回 True 表示連接成功，False 表示失敗。
        """
        try:
            self.api = dType.load() # 載入 Dobot DLL
            self.connect_status = dType.ConnectDobot(self.api, DOBOT_PORT, DOBOT_BAUDRATE)[0]
            if self.connect_status == dType.DobotConnect.DobotConnect_NoError:
                print(f"Dobot 連線成功: {DOBOT_CONNECT_STR[self.connect_status]}")
                self.is_connected = True
                self._initialize_dobot_params()
                self.go_home() # 連線成功後回歸原點
                return True
            else:
                print(f"Dobot 連線失敗: {DOBOT_CONNECT_STR[self.connect_status]}")
                self.is_connected = False
                return False
        except Exception as e:
            print(f"連接 Dobot 時發生錯誤: {e}")
            self.is_connected = False
            return False

    def _initialize_dobot_params(self):
        """
        初始化 Dobot 的運動參數。
        """
        if not self.is_connected:
            return

        dType.SetQueuedCmdClear(self.api) # 清除佇列中的所有指令
        # 設定 PTP 關節運動參數
        dType.SetPTPJointParams(self.api, 200, 200, 200, 200, 200, 200, 200, 200, isQueued=1)
        # 設定 PTP 座標運動參數
        dType.SetPTPCoordinateParams(self.api, 200, 200, 200, 200, isQueued=1)
        # 設定 PTP 通用參數 (速度和加速度百分比)
        dType.SetPTPCommonParams(self.api, 100, 100, isQueued=1)
        # 等待參數設定完成
        dType.SetWAITCmd(self.api, 1000, isQueued=1)
        self._wait_for_queue_completion()

    def _wait_for_queue_completion(self):
        """
        等待 Dobot 佇列中的所有指令執行完成。
        """
        if not self.is_connected:
            return
        dType.SetQueuedCmdStartExec(self.api) # 開始執行佇列指令
        while True:
            current_index = dType.GetQueuedCmdCurrentIndex(self.api)[0]
            max_index = dType.GetQueuedCmdMaxIndex(self.api)[0]
            # 當前執行指令索引達到佇列最大索引且最大索引不為 0 時，表示佇列已清空
            if max_index > 0 and current_index >= max_index:
                break
            # 如果佇列為空（max_index 為 0），也直接跳出
            if max_index == 0 and current_index == 0:
                break
            dType.dSleep(100) # 短暫延遲以避免高 CPU 佔用
        dType.SetQueuedCmdClear(self.api) # 清除佇列

    def go_home(self):
        """
        讓 Dobot 回到預設的歸位點。
        """
        if not self.is_connected:
            print("Dobot 未連線，無法執行歸位。")
            return
        print("Dobot 歸位中...")
        dType.SetHOMECmd(self.api, temp=0, isQueued=1) # 歸位指令
        self._wait_for_queue_completion()
        print("Dobot 已歸位。")

    def move_to(self, x, y, z, r=0, mode=dType.PTPMode.PTPMOVJXYZMode):
        """
        移動 Dobot 到指定的 XYZ 座標。
        """
        if not self.is_connected:
            return
        dType.SetPTPCmd(self.api, mode, x, y, z, r, isQueued=1)
        self._wait_for_queue_completion()

    def set_suction_cup(self, enable):
        """
        控制 Dobot 吸盤的開關。
        enable: True 為開啟吸盤，False 為關閉吸盤。
        """
        if not self.is_connected:
            return
        dType.SetEndEffectorSuctionCup(self.api, 1, int(enable), isQueued=1)
        self._wait_for_queue_completion()

    def run_conveyor(self, speed=12500, duration_ms=4850):
        """
        運行輸送帶一段時間。
        """
        if not self.is_connected:
            print("Dobot 未連線，無法運行輸送帶。")
            return
        print("輸送帶啟動中...")
        dType.SetEMotor(self.api, 0, 1, speed, 1) # 電機 0, 啟用, 速度, 佇列模式
        dType.SetWAITCmd(self.api, duration_ms, isQueued=1) # 等待指定時間
        dType.SetEMotor(self.api, 0, 1, 0, 1) # 停止電機
        self._wait_for_queue_completion()
        print("輸送帶已停止。")

    def pick_and_place(self, cX, cY, object_class):
        """
        執行物件的夾取和放置操作。
        cX, cY: 影像中的物件中心座標
        object_class: 物件的類別 (例如 'red', 'blue', 'broken')
        """
        if not self.is_connected:
            print("Dobot 未連線，無法執行夾取和放置。")
            return

        # 根據影像座標計算 Dobot 的世界座標 (此處的轉換係數非常重要，需校準)
        # 這些轉換係數 (0.5001383, 0.5043755, 0.4921233, 0.5138767) 是您原程式碼中的校準值
        # 它們決定了 Dobot 如何從像素座標映射到機械臂的毫米座標
        if (cY - Y_CENTER_OFFSET_VISION) >= 0:
            offy = (cY - Y_CENTER_OFFSET_VISION) * 0.5001383
        else:
            offy = (cY - Y_CENTER_OFFSET_VISION) * 0.5043755

        if (cX - X_CENTER_OFFSET_VISION) >= 0:
            offx = (X_CENTER_OFFSET_VISION - cX) * 0.4921233
        else:
            offx = (X_CENTER_OFFSET_VISION - cX) * 0.5138767

        obj_x = 268.3032 + offx
        obj_y = offy

        print(f"正在夾取 '{object_class}' 物件，影像座標=({cX}, {cY})，Dobot 座標=({obj_x:.2f}, {obj_y:.2f})")

        # 1. 接近物件，夾取並抬起
        self.move_to(obj_x, obj_y, HOVER_Z) # 移動到物件上方懸停高度
        self.move_to(obj_x, obj_y, PICK_Z)  # 下降到夾取高度
        self.set_suction_cup(True)          # 開啟吸盤
        time.sleep(0.5)                     # 給予吸盤足夠時間吸附
        self.move_to(obj_x, obj_y, HOVER_Z) # 抬起物件

        # 2. 移動到放置位置
        drop_coords = DROP_OFF_COORDINATES.get(object_class)
        if drop_coords:
            goal_x = drop_coords['x']
            goal_y = -drop_coords['y'] # Y 軸座標可能需要反轉，取決於您的 Dobot 安裝方向
            print(f"移動到放置點: ({goal_x:.2f}, {goal_y:.2f})")

            self.move_to(goal_x, goal_y, HOVER_Z) # 移動到放置點上方懸停
            self.move_to(goal_x, goal_y, DROP_Z)  # 下降到放置高度
            self.set_suction_cup(False)         # 關閉吸盤，釋放物件
            time.sleep(0.5)                     # 給予吸盤足夠時間釋放
            self.move_to(goal_x, goal_y, HOVER_Z) # 抬起

        else:
            print(f"警告：未定義 '{object_class}' 物件的放置座標，將在當前位置釋放。")
            self.set_suction_cup(False) # 關閉吸盤
            time.sleep(0.5)
            self.move_to(obj_x, obj_y, HOVER_Z) # 抬起

        self.go_home() # 回歸安全的原點位置

    def disconnect(self):
        """
        斷開與 Dobot 機械手臂的連線。
        """
        if self.is_connected and self.api:
            dType.SetQueuedCmdStopExec(self.api) # 停止佇列執行
            dType.DisconnectDobot(self.api)
            self.is_connected = False
            print("Dobot 已斷線。")