class YOLODetector:
    def __init__(self, model_path):
        from ultralytics import YOLO
        self.model = YOLO(str(model_path))

    def track(self, frame, **kwargs):
        return self.model.track(frame, **kwargs)
