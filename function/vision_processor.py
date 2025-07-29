import cv2
import numpy as np
from ultralytics import YOLO
from config import Video_num, kernel, color_map

class VisionProcessor:
    def __init__(self):
        self.model = YOLO("./Cube_Color_4_and_Defect_Model/V12_4_Color_Training12/weights/best.pt")
        self.capture = cv2.VideoCapture(Video_num)
        self.img_mask = None
        self._load_mask()
    
    def _load_mask(self):
        """載入遮罩圖片"""
        self.img_mask = cv2.imread("mask.png")
        if self.img_mask is None:
            print("無法載入 mask2.png，檢查文件是否存在")
    
    def adjust_gamma(self, image, gamma=1.0):
        """調整影像伽馬值"""
        invGamma = 1.0 / gamma
        table = np.array([((i / 255.0) ** invGamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
        return cv2.LUT(image, table)
    
    def process_frame(self):
        """處理單張影像並回傳檢測結果"""
        ret, cap_input = self.capture.read()
        if not ret:
            print("攝影機讀取失敗")
            return None, [], []
        
        print("原始影像尺寸:", cap_input.shape)
        
        # 應用遮罩
        if self.img_mask is not None:
            cap_mask = cv2.bitwise_and(cap_input, self.img_mask)
        else:
            cap_mask = cap_input.copy()
        
        print("遮罩後影像尺寸:", cap_mask.shape)
        
        # 處理HSV並找出contours
        hsv = cv2.cvtColor(cap_mask, cv2.COLOR_BGR2HSV)
        lower_black = np.array([0, 0, 99])
        upper_black = np.array([255, 255, 255])
        mask_black = cv2.inRange(hsv, lower_black, upper_black)
        mask_non_black = cv2.morphologyEx(mask_black, cv2.MORPH_OPEN, kernel)
        
        contours, _ = cv2.findContours(mask_non_black, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        # YOLO模型檢測
        results = self.model.track(cap_mask, persist=True, stream=True, conf=0.7)
        model_detected_objects = []
        unknown_detected_objects = []
        
        # 處理YOLO檢測結果
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
        
        # 處理未知物件（contours中未被YOLO檢測到的）
        for contour in contours:
            if cv2.contourArea(contour) < 500:
                continue
            edge = cv2.arcLength(contour, True)
            vertices = cv2.approxPolyDP(contour, edge * 0.04, True)
            x, y, w, h = cv2.boundingRect(vertices)
            x1, y1, x2, y2 = x, y, x + w, y + h

            is_known = False
            for obj in model_detected_objects:
                if (x1 >= obj['bbox'][0] - 20 and x2 <= obj['bbox'][2] + 20 and
                        y1 >= obj['bbox'][1] - 20 and y2 <= obj['bbox'][3] + 20):
                    is_known = True
                    break

            if not is_known:
                unknown_detected_objects.append({
                    'class': 'unknown',
                    'bbox': (x1, y1, x2, y2),
                    'center': ((x1 + x2) // 2, (y1 + y2) // 2)
                })
        
        # 在影像上繪製檢測框
        self._draw_detections(cap_input, model_detected_objects, unknown_detected_objects)
        
        return cap_input, model_detected_objects, unknown_detected_objects
    
    def _draw_detections(self, image, model_objects, unknown_objects):
        """在影像上繪製檢測框"""
        # 繪製YOLO檢測到的物件
        for obj in model_objects:
            x1, y1, x2, y2 = obj['bbox']
            box_color = color_map.get(obj['class'], (255, 255, 255))
            label = f"{obj['class']}"
            cv2.rectangle(image, (x1, y1), (x2, y2), box_color, 2)
            cv2.putText(image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        
        # 繪製未知物件
        for obj in unknown_objects:
            x1, y1, x2, y2 = obj['bbox']
            cv2.rectangle(image, (x1, y1), (x2, y2), (255, 255, 255), 2)
            cv2.putText(image, obj['class'], (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    
    def release(self):
        """釋放攝影機資源"""
        if self.capture:
            self.capture.release()