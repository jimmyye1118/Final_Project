from config import object_counts_init

class ObjectCounter:
    def __init__(self, socketio):
        self.socketio = socketio
        self.object_counts = object_counts_init.copy()
        self.total_objects = 0
        self.good_rate = 0.0
    
    def update_counts(self, class_name):
        """更新物件計數並傳送到前端"""
        self.object_counts[class_name] = self.object_counts.get(class_name, 0) + 1
        self.total_objects += 1
        good_objects = self.total_objects - self.object_counts.get('unknown', 0) - self.object_counts.get('broken', 0)
        self.good_rate = (good_objects / self.total_objects * 100) if self.total_objects > 0 else 0.0
        self.socketio.emit('object_counts', {
            'counts': self.object_counts,
            'total': self.total_objects,
            'good_rate': round(self.good_rate, 2)
        })
    
    def reset_counts(self):
        """重置計數"""
        self.object_counts = object_counts_init.copy()
        self.total_objects = 0
        self.good_rate = 0.0