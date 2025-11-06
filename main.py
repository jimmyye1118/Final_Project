import cv2
import base64
import time
import threading
import signal
import sys
from flask import Flask
from flask_socketio import SocketIO
import queue  # ⬅️ 1. 導入 queue

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
grab_option = 1  # 預設夾取選項，定點夾取
color_state = "None"
state = "None"
SLEEP_TIME = 0  # 移除不必要的延遲
CONVEYOR_SPEED = 50  # 例如：每秒 50 pixel
PREDICTION_TIME = 3.97  # 精確的預判時間：3.97 秒
PICKUP_DELAY = 0.87871  # 到達指定位置的時間：0.87871 秒
noweb_mode = False  # 新增：noweb 模式標記

# (NEW) 生產者-消費者 佇列
grab_queue = queue.Queue()

# (NEW) 簡易物件追蹤 (用於偵測跨線)
previous_frame_objects = {} # 儲存 { id: {'center': (cx, cy), 'class': 'blue'} }
next_object_id = 0
DETECTION_LINE_Y = 200      # 設定「偵測線」Y 座標
TRACKING_MAX_DIST = 65      # 追蹤時，兩幀之間允許的最大像素距離(可能之後再改，但不影響)

# 根據是否為 noweb 模式初始化 counter
if len(sys.argv) > 1 and sys.argv[1] == "noweb":
    noweb_mode = True
    counter = None  # noweb 模式下不使用 socketio
    print("🚀 啟動 noweb 模式")
else:
    counter = ObjectCounter(socketio)
    print("🌐 啟動 web 模式")

#4. 加入新的「消費者」執行緒 (grabber_thread_worker)
def grabber_thread_worker():
    """
    (NEW) 消費者執行緒
    專門從 grab_queue 拿任務，並呼叫 dobot 執行 (會阻塞)
    """
    global running, dobot, audio, PREDICTION_TIME
    
    print("🤖 夾取執行緒 (Consumer) 啟動... 等待任務...")
    
    while running:
        try:
            # get() 會自動阻塞 (睡著)，直到 queue 裡有東西
            # 拿到任務的同時，任務就從 queue 中 "移除" 了
            item = grab_queue.get() 
            
            if item is None:
                continue

            class_name = item['class']
            cross_time = item['cross_time']
            cross_x = item['cross_x'] # 拿到當時的 X 座標
            cross_y = item['cross_y'] # 拿到當時的 Y 座標]
            
            print(f"📦 [Consumer] 收到任務: {class_name}, 在 {cross_x} 跨線")

            # 1. 計算已經過了多久
            time_elapsed = time.time() - cross_time
            
            # 2. 我們還需要再等多久 (從偵測線到夾取點)
            wait_time = max(0, PREDICTION_TIME - time_elapsed)
            
            if wait_time > 0:
                print(f"⏳ [Consumer] 預判等待 {wait_time:.3f} 秒...")
                time.sleep(wait_time)
            
            # 3. 時間到，執行夾取 (呼叫我們在 dobot_controller 新增的函數)
            print(f"🤖 [Consumer] 時間到！執行夾取: {class_name}")
            
            # 播放音效
            if class_name in ['blue', 'yellow', 'green', 'red']:
                audio_map = {'blue': 11, 'yellow': 12, 'green': 13, 'red': 14}
                audio.speak(audio_map[class_name])
                
                # 呼叫新的、只管夾取的函數
                dobot.perform_predicted_grab(cross_x,cross_y, class_name, 8)
            
            elif class_name == 'broken':
                print("🔧 [Consumer] 處理破損物件 (跳過夾取)")
                audio.speak(16)
                # 破損物件，我們決定不夾，讓它流走
                # 如果要連輸送帶都停，邏輯會更複雜
            
        except Exception as e:
            print(f"❌ 夾取執行緒 (Consumer) 發生錯誤: {e}")

# 定點夾取
def process_object_fixed(model_objects, unknown_objects):
    """定點夾取處理函數"""
    
    for obj in model_objects:
        cX, cY = obj['center']
        class_name = obj['class']
        counter.update_counts(class_name)
        
        print(f"🎯 定點夾取: {class_name} at ({cX},{cY})")
        audio_map = {'blue': 11, 'yellow': 12, 'green': 13, 'red': 14}
        
        if class_name in audio_map:
            audio.speak(audio_map[class_name])
            time.sleep(0.8)
            dobot.dobot_fixed_work(cX, cY, class_name, 8)
        elif class_name == 'broken':
            audio.speak(16)
            dobot.run_fixed_conveyor()
            time.sleep(3) # 確保動作完成
    for obj in unknown_objects:
        print("🚨 定點異物處理中...")
        counter.update_counts('unknown')
        audio.speak(15)
        dobot.run_fixed_conveyor()
        time.sleep(1.5)


def main_loop():
    """主迴圈（非阻塞）"""
    global running, flag_start_work, counter,grab_option
    global previous_frame_objects, next_object_id, DETECTION_LINE_Y, grab_queue # (NEW)
    print("主迴圈啟動")
    
    # 初始化Dobot
    dobot.initialize()
    
    # noweb 模式自動開始工作
    if noweb_mode:
        print("noweb 模式：自動開始工作 (預設為定點)")
        flag_start_work = True
        grab_option = 1 # noweb 預設
    
    frame_count = 0

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
                
                # -----------------------------------------------
                # 模式一：定點夾取 
                # -----------------------------------------------
                if grab_option == 1:
                    model_objects.sort(key=lambda x: x['center'][0])
                    unknown_objects.sort(key=lambda x: x['center'][0])
                    process_object_fixed(model_objects, unknown_objects)
                    
                # -----------------------------------------------
                # 模式二：移動夾取 
                # -----------------------------------------------
                elif grab_option == 2:
                    
                    current_frame_objects = {} # 儲存 { id: {'center':(cx,cy), 'class':'blue'} }
                    
                    # 1. 整理這一幀的物件，並嘗試匹配上一幀的 ID
                    for obj in model_objects:
                        (cX, cY) = obj['center']
                        best_match_id = -1
                        min_dist = TRACKING_MAX_DIST # 最大允許距離
                        
                        for obj_id, prev_obj in previous_frame_objects.items():
                            dist = abs(cX - prev_obj['center'][0]) + abs(cY - prev_obj['center'][1])
                            if dist < min_dist:
                                min_dist = dist
                                best_match_id = obj_id
                        
                        if best_match_id != -1:
                            # A. 找到匹配，沿用 ID
                            current_frame_objects[best_match_id] = {'center': (cX, cY), 'class': obj['class']}
                            
                            # 檢查跨線事件
                            prev_y = previous_frame_objects[best_match_id]['center'][1]
                            if prev_y >= DETECTION_LINE_Y and cY < DETECTION_LINE_Y:
                                # 跨線！
                                print(f"📦 [Producer] 偵測到跨線: {obj['class']} (ID: {best_match_id})")
                                
                                # 檢查 (手臂是否空閒)
                                if grab_queue.qsize() == 0: #物理條件限制
                                    print("✅ [Producer] 手臂空閒，加入任務。")
                                    
                                    # 1. 計數 (只在這裡計數！)
                                    if counter:
                                        counter.update_counts(obj['class'])
                                        
                                    # 2. "記錄" (丟進 queue)
                                    task = {
                                        'class': obj['class'],
                                        'cross_time': current_time,
                                        'cross_x': cX,  # 記錄 "跨線時" 的 X 座標
                                        'cross_y': cY   # 記錄 "跨線時" 的 Y 座標
                                    }
                                    grab_queue.put(task)
                                
                                else:
                                    # 手臂還在忙！
                                    print(f"⚠️ [Producer] 手臂忙碌中 (Queue: {grab_queue.qsize()})，跳過此物件！")
                                
                        else:
                            # B. 找不到匹配，是新物件 (且還在線的上方)
                            if cY >= DETECTION_LINE_Y:
                                current_frame_objects[next_object_id] = {'center': (cX, cY), 'class': obj['class']}
                                next_object_id += 1
                    
                    # 3. 更新 "上一幀" 列表，供下一輪比對
                    previous_frame_objects = current_frame_objects.copy()   
                    
                    

            # 顯示影像
            cv2.imshow("camera_input", frame)
            socketio.sleep(0.1)  # 控制 WebSocket 傳輸頻率
            
            # 處理 OpenCV 視窗事件
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("使用者按下 'q'，結束程式")
                running = False
                break
            elif key == ord('s') and noweb_mode:
                flag_start_work = True
                grab_option = 1  # 預設為定點夾取
                print("🟢 開始工作")
            elif key == ord('p') and noweb_mode:
                flag_start_work = False
                print("🔴 暫停工作")
            
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
    
    # 停止消費者執行緒 (透過
    grab_queue.put(None) 
    
    cv2.destroyAllWindows()
    vision.release()
    dobot.disconnect() # disconnect 裡面會自動呼叫 stop_conveyor
    print("✅ 程式已清理並結束")

def signal_handler(sig, frame):
    """處理程式終止信號"""
    print("⚠️ 接收到終止信號")
    cleanup()
    exit(0)

# 接收前端控制指令（只在 web 模式下使用）
@socketio.on('control')
def handle_control(data):
    global flag_start_work, grab_option, previous_frame_objects, next_object_id
    command = data.get('command')
    print(f"📡 收到控制指令: {command}")
    if command == 'start':
        flag_start_work = True
        grab_option = 1  # 設定為定點夾取
        print("🟢 GO Work定點夾取")
        with grab_queue.mutex:
            grab_queue.queue.clear()
    elif command == 'move_grasp':
        flag_start_work = True
        grab_option = 2
        print("🟡 移動夾取選項已選擇")
        # (清空 queue 和追蹤器)
        with grab_queue.mutex:
            grab_queue.queue.clear()
        previous_frame_objects.clear()
        next_object_id = 0
        
        # 啟動輸送帶
        dobot.start_conveyor()
        
    elif command == 'stop':
        flag_start_work = False
        print("🔴 Finish")
        
        # 關鍵：停止輸送帶
        dobot.stop_conveyor()
        
        # (清空 queue)
        with grab_queue.mutex:
            grab_queue.queue.clear()

    elif command == 'reset':
        # (清空 queue 和追蹤器)
        with grab_queue.mutex:
            grab_queue.queue.clear()
        previous_frame_objects.clear()
        next_object_id = 0
        print("🔄 重置佇列與追蹤器")


@socketio.on('Recorder_control')
def handle_recorder_control(data):
    global voice_recognizer, flag_start_work, grab_option
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
                grab_option = 1  # 設定為定點夾取
                print("🟢 GO Work定點夾取")
                with grab_queue.mutex:
                    grab_queue.queue.clear()
                print("語音指令：啟動工作")
                
            elif recognized_command == 'stop':
                flag_start_work = False
                print("🔴 Finish")
        
                # 關鍵：停止輸送帶
                dobot.stop_conveyor()
        
                # (清空 queue)
                with grab_queue.mutex:
                    grab_queue.queue.clear()
            elif recognized_command in ['red', 'blue', 'yellow', 'green']:
                # 這裡可以根據顏色指令執行機械手臂的特定動作
                print(f"語音指令: 執行 {recognized_command} 色分類動作")
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
    # ... (其他 print 不變) ...
    print(f"🧬 偵測線 Y 座標: {DETECTION_LINE_Y}")
    print("=" * 50)

    # ⬅️ 關鍵：在這裡啟動「消費者」執行緒
    # 讓它在背景開始睡覺 (等待任務)
    print("🚀 啟動消費者 (Grabber) 執行緒...")
    threading.Thread(target=grabber_thread_worker, daemon=True).start()

    # 判斷是否傳入 "noweb" 模式
    if noweb_mode:
        try:
            # noweb 模式，直接執行主迴圈
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