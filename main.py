# main.py

from flask import Flask, render_template
from flask_socketio import SocketIO
import threading
import signal
import cv2
import base64
import time

# main.py
from config import PYTHON_SOCKET_IO_PORT, PYTHON_SOCKET_IO_HOST # 如果config在根目錄，這樣導入是正確的
from function.dobot_controller import DobotController
from function.vision_system import VisionSystem
from function.utils import speak

class ObjectSortingApp:
    """
    機械手臂自動分揀系統的主應用程式。
    負責協調視覺系統、Dobot 機械手臂和網頁介面的通訊。
    """
    def __init__(self):
        self.app = Flask(__name__)
        # 設定 Flask 的模板目錄 (如果 index.html 不在根目錄，例如在 public/ 下)
        # self.app = Flask(__name__, template_folder='public')
        self.app.add_url_rule('/', 'index', self.index) # 設置根路徑對應的處理函數

        # 初始化 Flask-SocketIO，允許所有來源 (開發階段方便，生產環境請限制)
        self.socketio = SocketIO(self.app, cors_allowed_origins="*")

        self.dobot = DobotController()
        self.vision = VisionSystem()

        self.running = False # 控制主迴圈運行狀態
        self.flag_start_work = False # 控制 Dobot 工作啟動/停止

        # 物件計數統計
        self.object_counts = {
            'red': 0, 'blue': 0, 'yellow': 0, 'green': 0, 'broken': 0, 'unknown': 0
        }
        self.total_objects = 0
        self.good_rate = 0.0

        self._register_socketio_events() # 註冊 Socket.IO 事件處理器
        self._setup_signal_handler() # 設置信號處理器，用於程式優雅退出

    def index(self):
        """
        渲染主網頁 (index.html)。
        """
        # 如果 index.html 在 public/ 資料夾內，請確保 Flask 知道其模板位置
        # 或直接使用 send_from_directory
        return render_template('index.html')

    def _register_socketio_events(self):
        """
        註冊 Socket.IO 事件處理器，處理前端的連接、斷開和控制指令。
        """
        @self.socketio.on('connect')
        def on_connect():
            print("WebSocket 客戶端已連線。")
            if not self.running:
                self.running = True
                # 在新執行緒中啟動主迴圈，daemon=True 確保主程式退出時該執行緒也會結束
                threading.Thread(target=self.main_loop, daemon=True).start()
                print("主迴圈已啟動。")
            self.dobot.connect() # 當有客戶端連線時嘗試連接 Dobot

        @self.socketio.on('disconnect')
        def on_disconnect():
            print("WebSocket 客戶端已斷線。")
            # 考慮是否在每次斷線時清理，或者只在應用程式關閉時清理
            # 如果清理，下一次連接時需要重新初始化 Dobot 和攝影機

        @self.socketio.on('control')
        def handle_control(data):
            command = data.get('command')
            print(f"收到控制指令: {command}")
            if command == 'start':
                if not self.flag_start_work:
                    self.flag_start_work = True
                    print("開始工作...")
            elif command == 'stop':
                if self.flag_start_work:
                    self.flag_start_work = False
                    print("停止工作。")

    def _setup_signal_handler(self):
        """
        設置系統信號處理器，用於捕獲 Ctrl+C 等終止信號，實現優雅關閉。
        """
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, sig, frame):
        """
        處理終止信號，呼叫清理函數並退出程式。
        """
        print("收到終止信號。正在執行清理動作...")
        self.cleanup()
        exit(0)

    def update_counts(self, class_name):
        """
        更新物件計數統計，並透過 Socket.IO 發送給前端。
        """
        self.object_counts[class_name] = self.object_counts.get(class_name, 0) + 1
        self.total_objects += 1
        # 計算良好物件數 (總數 - 破損數 - 未知數)
        good_objects = self.total_objects - self.object_counts.get('unknown', 0) - self.object_counts.get('broken', 0)
        # 計算良好率，避免除以零
        self.good_rate = (good_objects / self.total_objects * 100) if self.total_objects > 0 else 0.0
        # 發送統計數據到前端
        self.socketio.emit('object_counts', {
            'counts': self.object_counts,
            'total': self.total_objects,
            'good_rate': round(self.good_rate, 2)
        })

    def main_loop(self):
        """
        應用程式的主執行迴圈。
        負責不斷讀取影像、處理物件、執行 Dobot 操作並更新前端。
        """
        print("主迴圈已啟動。")
        while self.running:
            ret, cap_input = self.vision.read_frame()
            if not ret:
                time.sleep(1) # 如果讀取失敗，等待一段時間後重試
                continue

            # 處理影像，獲取已偵測物件和未知物件
            model_detected_objects, unknown_detected_objects, original_frame = self.vision.process_frame(cap_input)
            # 在影像上繪製偵測結果
            display_frame = self.vision.draw_detections(original_frame, model_detected_objects, unknown_detected_objects)

            # 將處理後的影像轉換為 JPG 格式的 Base64 字串，並發送給前端
            _, buffer = cv2.imencode('.jpg', display_frame)
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            self.socketio.emit('frame', {'frame': jpg_as_text})

            # 如果工作已啟動且 Dobot 已連線
            if self.flag_start_work and self.dobot.is_connected:
                # 將所有偵測到的物件合併並按 X 座標排序 (從左到右處理)
                all_detected_objects = sorted(
                    model_detected_objects + unknown_detected_objects,
                    key=lambda x: x['center'][0]
                )

                for obj in all_detected_objects:
                    class_name = obj['class']
                    cX, cY = obj['center']
                    self.update_counts(class_name) # 更新前端統計數據

                    # 根據物件類別執行 Dobot 操作和播放音效
                    if class_name == 'blue':
                        speak(11)
                        time.sleep(1)
                        self.dobot.pick_and_place(cX, cY, class_name)
                    elif class_name == 'yellow':
                        speak(12)
                        time.sleep(1)
                        self.dobot.pick_and_place(cX, cY, class_name)
                    elif class_name == 'green':
                        speak(13)
                        time.sleep(1)
                        self.dobot.pick_and_place(cX, cY, class_name)
                    elif class_name == 'red':
                        speak(14)
                        time.sleep(1)
                        self.dobot.pick_and_place(cX, cY, class_name)
                    elif class_name == 'broken': # 破損物件
                        speak(16)
                        time.sleep(1)
                        self.dobot.run_conveyor(duration_ms=4850) # 運行輸送帶排除
                    elif class_name == 'unknown': # 未知物件
                        speak(15)
                        time.sleep(1)
                        self.dobot.run_conveyor(duration_ms=5000) # 運行輸送帶排除
                    time.sleep(0.5) # 每個物件處理後的短暫延遲

                # 如果沒有偵測到物件，可以考慮讓輸送帶短暫運行，以帶入新物件
                if not all_detected_objects:
                    # 可選：self.dobot.run_conveyor(speed=5000, duration_ms=1000)
                    time.sleep(0.5) # 防止沒有物件時 CPU 忙等

            cv2.imshow("攝影機畫面", display_frame) # 在本地顯示攝影機畫面

            # 監聽鍵盤 'q' 鍵，用於手動退出程式
            if cv2.waitKey(1) & 0xFF == ord('q'):
                print("按下 'q' 鍵，正在關閉程式。")
                self.cleanup()
                break

            self.socketio.sleep(0.05) # 控制 WebSocket 傳輸頻率，並釋放 CPU

        self.cleanup() # 確保主迴圈退出時進行清理

    def cleanup(self):
        """
        執行應用程式退出前的清理工作，例如釋放攝影機和斷開 Dobot 連線。
        """
        print("正在清理資源...")
        self.running = False
        self.vision.release() # 釋放攝影機
        self.dobot.disconnect() # 斷開 Dobot
        cv2.destroyAllWindows() # 關閉所有 OpenCV 視窗
        print("應用程式已清理並終止。")

    def run(self):
        """
        啟動 Flask-SocketIO 伺服器。
        """
        print(f"Flask-SocketIO 伺服器運行於 http://{PYTHON_SOCKET_IO_HOST}:{PYTHON_SOCKET_IO_PORT}")
        # allow_unsafe_werkzeug=True 在開發環境中是允許的，生產環境請考慮更安全的方式
        self.socketio.run(self.app, host=PYTHON_SOCKET_IO_HOST, port=PYTHON_SOCKET_IO_PORT, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    # 創建應用程式實例並運行
    app = ObjectSortingApp()
    app.run()