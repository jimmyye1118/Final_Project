import cv2
import base64
import time
import threading
import signal
from flask import Flask
from flask_socketio import SocketIO

from function.dobot_controller import DobotController
from function.vision_processor import VisionProcessor
from function.audio_controller import AudioController
from function.object_counter import ObjectCounter

app = Flask(__name__)
socketio = SocketIO(app)

# 初始化各模組
dobot = DobotController()
vision = VisionProcessor()
audio = AudioController()
counter = ObjectCounter(socketio)

# 控制變數
running = True
flag_start_work = False
color_state = "None"
state = "None"

def main_loop():
    """主迴圈（非阻塞）"""
    global running, flag_start_work
    print("主迴圈啟動")
    
    # 初始化Dobot
    dobot.initialize()

    while running:
        # 處理影像
        frame, model_objects, unknown_objects = vision.process_frame()
        if frame is None:
            print("攝影機讀取失敗，退出主迴圈")
            break

        # 傳送影像到前端
        _, buffer = cv2.imencode('.jpg', frame)
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        print(f"傳送影像大小: {len(jpg_as_text)} 字元")
        socketio.emit('frame', {'frame': jpg_as_text})

        # 如果開始工作模式
        if flag_start_work:
            # 按X座標排序
            model_objects.sort(key=lambda x: x['center'][0])
            unknown_objects.sort(key=lambda x: x['center'][0])
            # print("7777777777777777777777777777777777777")
            # 處理已知物件
            for obj in model_objects:
                cX, cY = obj['center']
                class_name = obj['class']
                counter.update_counts(class_name)

                if class_name == 'blue':
                    color_state = "blue"
                    audio.speak(11)
                    time.sleep(1)
                    dobot.dobot_work(cX, cY, class_name, 8)
                elif class_name == 'yellow':
                    color_state = "yellow"
                    audio.speak(12)
                    time.sleep(1)
                    dobot.dobot_work(cX, cY, class_name, 8)
                elif class_name == 'green':
                    color_state = "green"
                    audio.speak(13)
                    time.sleep(1)
                    dobot.dobot_work(cX, cY, class_name, 8)
                elif class_name == 'red':
                    color_state = "red"
                    audio.speak(14)
                    time.sleep(1)
                    dobot.dobot_work(cX, cY, class_name, 8)
                elif class_name == 'broken':
                    audio.speak(16)
                    time.sleep(1)
                    dobot.run_conveyor()
                    time.sleep(4)
                time.sleep(1)

            # 處理未知物件
            for obj in unknown_objects:
                counter.update_counts('unknown')
                print("檢測到異物，運行輸送帶")
                audio.speak(15)
                time.sleep(1)
                dobot.run_conveyor()
                time.sleep(5)

        cv2.imshow("camera_input", frame)
        socketio.sleep(0.1)  # 控制 WebSocket 傳輸頻率

    # 清理
    cleanup()

def cleanup():
    """清理函數"""
    global running
    running = False
    cv2.destroyAllWindows()
    vision.release()
    dobot.disconnect()
    print("程式已清理並結束")

def signal_handler(sig, frame):
    """處理程式終止信號"""
    cleanup()
    exit(0)

# 接收前端控制指令
@socketio.on('control')
def handle_control(data):
    global flag_start_work
    command = data.get('command')
    print(f"收到控制指令: {command}")
    if command == 'start':
        flag_start_work = True
        print("GO Work")
    elif command == 'stop':
        flag_start_work = False
        print("Finish")

@socketio.on('connect')
def on_connect():
    print("WebSocket 客戶端已連線")
    global running
    running = True
    threading.Thread(target=main_loop, daemon=True).start()

@socketio.on('disconnect')
def on_disconnect():
    print("WebSocket 客戶端已斷線")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    socketio.run(app, host='0.0.0.0', port=5000)