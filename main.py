import cv2
import base64
import time
import threading
import signal
from flask import Flask
from flask_socketio import SocketIO

from function.voice_recognizer import VoiceRecognizer
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
voice_recognizer = VoiceRecognizer() # 初始化語音辨識模組

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

@socketio.on('Recorder_control')
def handle_recorder_control(data):
    global voice_recognizer, flag_start_work
    command = data.get('command')
    print(f"收到語音錄音指令: {command}")

    if command == 'voice_start_record':
        voice_recognizer.start_recording()
        # 語音開始錄音時，前端會更新狀態，後端不需要額外回傳
    elif command == 'voice_stop_record':
        # recognized_command = voice_recognizer.stop_recording()
        recognized_command, recognized_text = voice_recognizer.stop_recording()
        if recognized_command:
            # 如果辨識成功，將結果回傳給前端
            socketio.emit('voice_status', {'text': f'辨識結果: {recognized_text}', 'command': recognized_command})
            print(f"語音辨識結果: {recognized_command}") #接收指令為keyword_action 右邊。

            # 根據語音辨識結果執行動作
            if recognized_command == 'start':
                flag_start_work = True
                print("語音指令：啟動工作")
                audio.speak("開始工作") # 可以加入語音回饋
            elif recognized_command == 'stop':
                flag_start_work = False
                print("語音指令：停止工作")
                audio.speak("工作已停止") # 可以加入語音回饋
            elif recognized_command in ['red', 'blue', 'yellow', 'green']:
                # 這裡可以根據顏色指令執行機械手臂的特定動作
                print(f"語音指令: 執行 {recognized_command} 色分類動作")
                audio.speak(f"已收到{recognized_command}色指令")
                # dobot.dobot_work(..., recognized_command, ...)
                # 注意：這裡僅為範例，實際執行動作需要物件資訊
            else:
                print(f"語音指令 {recognized_command} 未對應到預設動作")
                audio.speak("指令無法理解")
        else:
            # 如果沒有辨識到有效指令，回傳訊息給前端
            socketio.emit('voice_status', {'text': '未辨識到有效指令'})
            print("語音辨識：未辨識到有效指令")
            audio.speak("沒有聽清楚，請再說一次")
    else:
        print(f"⚠️ 無效的 Recorder_control 指令：{command}")



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