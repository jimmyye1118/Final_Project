import cv2
import base64
import time
import threading
import signal
import sys
from flask import Flask
from flask_socketio import SocketIO

from function.voice_recognizer import VoiceRecognizer
from function.dobot_controller import DobotController
from function.vision_processor import VisionProcessor
from function.audio_controller import AudioController
from function.object_counter import ObjectCounter

# 全域變數宣告
app = Flask(__name__)
socketio = SocketIO(app)

# 初始化各模組
dobot = DobotController()
vision = VisionProcessor()
audio = AudioController()
voice_recognizer = VoiceRecognizer() # 初始化語音辨識模組

# 控制變數
running = True
flag_start_work = False
color_state = "None"
state = "None"
SLEEP_TIME = 0  # 移除不必要的延遲
CONVEYOR_SPEED = 50  # 例如：每秒 50 pixel
PREDICTION_TIME = 0.87871  # 精確的預判時間：0.87871 秒
PICKUP_DELAY = 0.87871  # 到達指定位置的時間：0.87871 秒
noweb_mode = False  # 新增：noweb 模式標記

# 處理中的物件記錄（避免重複處理）
processed_objects = set()
processing_lock = threading.Lock()

# 根據是否為 noweb 模式初始化 counter
if len(sys.argv) > 1 and sys.argv[1] == "noweb":
    noweb_mode = True
    counter = None  # noweb 模式下不使用 socketio
    print("🚀 啟動 noweb 模式")
else:
    counter = ObjectCounter(socketio)
    print("🌐 啟動 web 模式")

def get_object_id(obj):
    """生成物件唯一ID（基於位置和類別）"""
    cX, cY = obj['center']
    class_name = obj['class']
    # 使用粗略位置避免微小位移造成的重複ID
    rough_x = round(cX / 20) * 20
    rough_y = round(cY / 20) * 20
    return f"{class_name}_{rough_x}_{rough_y}"

def process_object_async(obj, detection_time):
    """異步處理物件（避免阻塞主迴圈）"""
    global processed_objects
    
    cX, cY = obj['center']
    class_name = obj['class']
    obj_id = get_object_id(obj)
    
    # 檢查是否已經處理過
    with processing_lock:
        if obj_id in processed_objects:
            return
        processed_objects.add(obj_id)
    
    try:
        print(f"🎯 開始處理物件: {class_name} at ({cX}, {cY})")
        
        # 計算預判位置
        time_elapsed = time.time() - detection_time
        predicted_cY = cY - CONVEYOR_SPEED * (PREDICTION_TIME + time_elapsed)
        
        print(f"📍 預判位置: ({cX}, {predicted_cY:.2f}), 延遲: {time_elapsed:.3f}s")
        
        # 只在有 counter 時更新計數
        if counter is not None:
            counter.update_counts(class_name)
        
        # 等待到達最佳夾取時機
        wait_time = PICKUP_DELAY - time_elapsed
        if wait_time > 0:
            print(f"⏳ 等待 {wait_time:.3f} 秒到達最佳夾取位置")
            time.sleep(wait_time)
        
        # 處理不同顏色的物件
        if class_name in ['blue', 'yellow', 'green', 'red']:
            color_state = class_name
            
            # 播放對應音效（非阻塞）
            audio_map = {'blue': 11, 'yellow': 12, 'green': 13, 'red': 14}
            audio.speak(audio_map[class_name])
            
            # 執行夾取動作
            print(f"🤖 執行夾取: {class_name}")
            dobot.dobot_work(cX, predicted_cY, class_name, 8)
            
        elif class_name == 'broken':
            print("🔧 處理破損物件")
            audio.speak(16)
            dobot.run_conveyor()
            
        print(f"✅ 物件處理完成: {class_name}")
        
    except Exception as e:
        print(f"❌ 處理物件時發生錯誤: {e}")
    finally:
        # 清理處理記錄（一段時間後）
        def cleanup_processed_id():
            time.sleep(10)  # 10秒後清理
            with processing_lock:
                if obj_id in processed_objects:
                    processed_objects.discard(obj_id)
        
        threading.Thread(target=cleanup_processed_id, daemon=True).start()

def main_loop():
    """主迴圈（非阻塞）"""
    global running, flag_start_work, counter
    print("主迴圈啟動")
    
    # 初始化Dobot
    dobot.initialize()
    
    # noweb 模式自動開始工作
    if noweb_mode:
        print("noweb 模式：自動開始工作")
        flag_start_work = True
    
    frame_count = 0
    last_detection_time = time.time()

    while running:
        try:
            frame_count += 1
            current_time = time.time()
            
            # 處理影像
            frame, model_objects, unknown_objects = vision.process_frame()
            if frame is None:
                print("攝影機讀取失敗，等待恢復...")
                time.sleep(0.1)
                continue

            # 只在 web 模式下傳送影像到前端
            if not noweb_mode and frame_count % 3 == 0:  # 降低傳輸頻率
                _, buffer = cv2.imencode('.jpg', frame)
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                socketio.emit('frame', {'frame': jpg_as_text})

            # 如果開始工作模式
            if flag_start_work:
                # 處理已知物件
                if model_objects:
                    last_detection_time = current_time
                    print(f"🔍 檢測到 {len(model_objects)} 個物件")
                    
                    # 按X座標排序（處理最前面的物件）
                    model_objects.sort(key=lambda x: x['center'][0])
                    
                    # 異步處理每個物件
                    for obj in model_objects:
                        threading.Thread(
                            target=process_object_async, 
                            args=(obj, current_time), 
                            daemon=True
                        ).start()
                
                # 處理未知物件
                if unknown_objects:
                    print(f"⚠️ 檢測到 {len(unknown_objects)} 個未知物件")
                    for obj in unknown_objects:
                        obj_id = get_object_id(obj)
                        
                        with processing_lock:
                            if obj_id not in processed_objects:
                                processed_objects.add(obj_id)
                                
                                if counter is not None:
                                    counter.update_counts('unknown')
                                
                                print("🚨 檢測到異物，處理中...")
                                audio.speak(15)
                                
                                # 異步處理異物
                                def handle_unknown():
                                    dobot.run_conveyor()
                                
                                threading.Thread(target=handle_unknown, daemon=True).start()

            # 顯示影像
            cv2.imshow("camera_input", frame)
            
            # 處理 OpenCV 視窗事件
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("使用者按下 'q'，結束程式")
                running = False
                break
            elif key == ord('s') and noweb_mode:
                flag_start_work = True
                print("🟢 開始工作")
            elif key == ord('p') and noweb_mode:
                flag_start_work = False
                print("🔴 暫停工作")
            elif key == ord('r') and noweb_mode:
                # 重置處理記錄
                with processing_lock:
                    processed_objects.clear()
                print("🔄 重置處理記錄")
            
            # 顯示運行狀態
            if frame_count % 100 == 0:  # 每100幀顯示一次狀態
                status = "🟢 運行中" if flag_start_work else "🔴 暫停中"
                print(f"📊 狀態: {status}, 幀數: {frame_count}, 處理中物件: {len(processed_objects)}")
            
            # 控制迴圈頻率
            if noweb_mode:
                time.sleep(0.01)  # 提高處理頻率
            else:
                socketio.sleep(0.03)
                
        except Exception as e:
            print(f"❌ 主迴圈錯誤: {e}")
            time.sleep(0.1)

    # 清理
    cleanup()

def cleanup():
    """清理函數"""
    global running
    running = False
    print("🧹 開始清理資源...")
    cv2.destroyAllWindows()
    vision.release()
    dobot.disconnect()
    print("✅ 程式已清理並結束")

def signal_handler(sig, frame):
    """處理程式終止信號"""
    print("⚠️ 接收到終止信號")
    cleanup()
    exit(0)

# 接收前端控制指令（只在 web 模式下使用）
@socketio.on('control')
def handle_control(data):
    global flag_start_work
    command = data.get('command')
    print(f"📡 收到控制指令: {command}")
    if command == 'start':
        flag_start_work = True
        print("🟢 GO Work")
    elif command == 'stop':
        flag_start_work = False
        print("🔴 Finish")
    elif command == 'reset':
        with processing_lock:
            processed_objects.clear()
        print("🔄 重置處理記錄")


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
    print("🔌 WebSocket 客戶端已連線")
    global running
    running = True
    threading.Thread(target=main_loop, daemon=True).start()

@socketio.on('disconnect')
def on_disconnect():
    print("🔌 WebSocket 客戶端已斷線")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    print("=" * 50)
    print("🤖 機械手臂連續運行系統啟動")
    print("=" * 50)
    print(f"📊 輸送帶速度: {CONVEYOR_SPEED} 像素/秒")
    print(f"⏱️ 預判時間: {PREDICTION_TIME} 秒")
    print(f"🎯 夾取延遲: {PICKUP_DELAY} 秒")
    print(f"💤 睡眠時間: {SLEEP_TIME} 秒")
    
    if noweb_mode:
        print("🔧 模式: noweb (無網頁介面)")
        print("⌨️ 控制說明:")
        print("   - 按 'q' 退出程式")
        print("   - 按 's' 開始工作")
        print("   - 按 'p' 暫停工作")
        print("   - 按 'r' 重置處理記錄")
        print("   - Ctrl+C 強制退出")
    else:
        print("🌐 模式: web (含網頁介面)")
        print("🔗 WebSocket 埠號: 5000")
    
    print("=" * 50)

    # 判斷是否傳入 "noweb" 模式
    if noweb_mode:
        try:
            # 直接執行主迴圈，不開 Flask server
            main_loop()
        except KeyboardInterrupt:
            print("⚠️ 接收到 Ctrl+C，正在關閉程式...")
            cleanup()
    else:
        # 正常啟動 WebSocket + Flask
        try:
            socketio.run(app, host='0.0.0.0', port=5000)
        except KeyboardInterrupt:
            print("⚠️ 接收到 Ctrl+C，正在關閉 Flask 伺服器...")
            cleanup()