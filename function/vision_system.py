# vision_system.py

import cv2
import numpy as np
from ultralytics import YOLO
from config import (VIDEO_SOURCE, MODEL_PATH, MASK_IMAGE_PATH, GAMMA_VALUE,
                    CONFIDENCE_THRESHOLD, MIN_CONTOUR_AREA, BOUNDING_BOX_PADDING,
                    COLOR_MAP, KERNEL_SIZE)
from .utils import adjust_gamma

class VisionSystem:
    """
    處理攝影機影像擷取、物件偵測 (YOLO) 和影像處理。
    """
    def __init__(self):
        self.capture = None
        self.model = YOLO(MODEL_PATH)
        self.img_mask = None
        self.kernel = np.ones(KERNEL_SIZE, np.uint8) # 形態學操作的核
        self._load_mask()
        self._init_camera()

    def _load_mask(self):
        """
        載入用於影像區域篩選的遮罩圖片。
        如果找不到遮罩圖片，則建立一個空白遮罩並發出警告。
        """
        self.img_mask = cv2.imread(MASK_IMAGE_PATH)
        if self.img_mask is None:
            print(f"警告：無法載入遮罩圖片 '{MASK_IMAGE_PATH}'。請檢查檔案是否存在。")
            print("將使用預設的黑色遮罩，影像處理將會是全畫面。")
            # 暫時建立一個預設大小的黑色遮罩，之後會根據攝影機解析度調整
            self.img_mask = np.zeros((480, 640, 3), dtype=np.uint8)

    def _init_camera(self):
        """
        初始化攝影機擷取。如果失敗會嘗試重新初始化。
        """
        self.capture = cv2.VideoCapture(VIDEO_SOURCE)
        if not self.capture.isOpened():
            print(f"錯誤：無法開啟視訊來源 {VIDEO_SOURCE}。請檢查攝影機是否連線或被佔用。")
            self.capture = None
        else:
            print(f"攝影機 {VIDEO_SOURCE} 初始化成功。")
            # 如果之前是預設黑色遮罩，則更新其大小以匹配攝影機解析度
            if self.img_mask.shape[0] == 480 and self.img_mask.shape[1] == 640:
                width = int(self.capture.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(self.capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if width > 0 and height > 0:
                    self.img_mask = np.zeros((height, width, 3), dtype=np.uint8)
                    print(f"已將預設遮罩調整為攝影機解析度：{width}x{height}")

    def read_frame(self):
        """
        從攝影機讀取一幀影像。
        返回 (ret, frame) 元組，ret 表示是否成功讀取，frame 是讀取的影像。
        如果讀取失敗會嘗試重新初始化攝影機。
        """
        if self.capture is None:
            return False, None
        ret, frame = self.capture.read()
        if not ret:
            print("無法讀取攝影機幀。嘗試重新初始化攝影機。")
            self._init_camera() # 嘗試重新初始化
            return False, None
        return ret, frame

    def process_frame(self, frame):
        """
        對單一影像幀進行物件偵測和處理。
        包括應用遮罩、Gamma 調整、YOLO 偵測和輪廓分析以識別未知物件。
        返回 (已偵測物件列表, 未知物件列表, 原始影像幀)。
        """
        # 應用遮罩，篩選出感興趣的區域
        if self.img_mask is None:
            cap_mask = frame # 如果遮罩載入失敗，則使用原始影像
        else:
            # 確保遮罩和影像尺寸一致
            if frame.shape != self.img_mask.shape:
                print(f"警告：影像尺寸 {frame.shape} 與遮罩尺寸 {self.img_mask.shape} 不匹配。正在調整遮罩尺寸。")
                self.img_mask = cv2.resize(self.img_mask, (frame.shape[1], frame.shape[0]))
            cap_mask = cv2.bitwise_and(frame, self.img_mask)

        # 調整影像亮度
        processed_frame = adjust_gamma(cap_mask, GAMMA_VALUE)

        # 使用 YOLO 進行物件偵測
        results = self.model.track(processed_frame, persist=True, stream=True, conf=CONFIDENCE_THRESHOLD)

        model_detected_objects = []
        for r in results:
            boxes = r.boxes
            for box in boxes:
                class_name = r.names[int(box.cls[0])].lower()
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                model_detected_objects.append({
                    'class': class_name,
                    'bbox': (x1, y1, x2, y2),
                    'confidence': conf,
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })

        # 使用輪廓分析識別未知物件 (非 YOLO 模型預設類別的物件)
        hsv = cv2.cvtColor(processed_frame, cv2.COLOR_BGR2HSV)
        # 過濾掉黑色背景，找到可能是物件的區域
        lower_black = np.array([0, 0, 99])
        upper_black = np.array([255, 255, 255])
        mask_black = cv2.inRange(hsv, lower_black, upper_black)
        mask_non_black = cv2.morphologyEx(mask_black, cv2.MORPH_OPEN, self.kernel) # 形態學開運算去除噪點

        contours, _ = cv2.findContours(mask_non_black, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        unknown_detected_objects = []
        for contour in contours:
            if cv2.contourArea(contour) < MIN_CONTOUR_AREA: # 過濾掉太小的輪廓
                continue
            x, y, w, h = cv2.boundingRect(contour)
            x1, y1, x2, y2 = x, y, x + w, y + h

            is_known = False
            for obj in model_detected_objects:
                # 檢查當前輪廓是否與 YOLO 偵測到的已知物件重疊
                if (x1 >= obj['bbox'][0] - BOUNDING_BOX_PADDING and x2 <= obj['bbox'][2] + BOUNDING_BOX_PADDING and
                    y1 >= obj['bbox'][1] - BOUNDING_BOX_PADDING and y2 <= obj['bbox'][3] + BOUNDING_BOX_PADDING):
                    is_known = True
                    break
            if not is_known:
                unknown_detected_objects.append({
                    'class': 'unknown',
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })

        return model_detected_objects, unknown_detected_objects, frame

    def draw_detections(self, frame, model_objects, unknown_objects):
        """
        在影像幀上繪製偵測到的物件的邊界框和標籤。
        返回繪製後的影像幀。
        """
        display_frame = frame.copy() # 在影像副本上操作，不修改原始影像

        for obj in model_objects:
            x1, y1, x2, y2 = obj['bbox']
            box_color = COLOR_MAP.get(obj['class'], (255, 255, 255)) # 根據類別獲取顏色
            label = f"{obj['class']}" # 可選：f"{obj['class']} {obj['confidence']:.2f}"
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)

        for obj in unknown_objects:
            x1, y1, x2, y2 = obj['bbox']
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), COLOR_MAP.get('unknown'), 2)
            cv2.putText(display_frame, obj['class'], (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        return display_frame

    def release(self):
        """
        釋放攝影機資源。
        """
        if self.capture:
            self.capture.release()
            print("攝影機資源已釋放。")