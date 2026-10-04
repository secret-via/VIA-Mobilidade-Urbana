import time
from collections import Counter, deque

import cv2
import numpy as np

from config.config import (
    CONFIDENCE,
    COUNTING_LINES,
    INFERENCE_IMGSZ,
    STOP_THRESHOLD,
    STOP_TIME,
    TRACKER,
    TRAIL_LENGTH,
    LEARNING_ENABLED,
    LOW_CONFIDENCE_THRESHOLD,
    INTERMEDIATE_CONFIDENCE_THRESHOLD,
    MIN_LEARNING_INTERVAL,
    MAX_LEARNING_CASES,
    MODEL_VERSION,
    ROLLING_WINDOW_SECONDS,
)

from agent.agent import TrafficAgent
from agent.memory import AgentMemory
from learning.collector import CaseCollector
from learning.sampler import LearningSampler
from traffic.events import EventLogger
from utils.counting import LineCounter
from utils.tracking import TrackHistory
from utils.traffic import calculate_congestion


class TrafficProcessor:
    """Processa cada frame e mantém o snapshot consumido pelo dashboard.

    O vídeo recebe apenas caixas, rótulo curto e trilha: nenhuma estatística
    agregada nem linha de contagem é desenhada na imagem. Todas as métricas
    (contagens, fluxo, congestionamento, explicação do agente) vão para
    `last_snapshot`, que o dashboard expõe via API/WebSocket para a interface
    renderizar.
    """

    def __init__(self, model, lines=COUNTING_LINES, camera_id=None, org_id=None):
        self.model = model
        self.camera_id = camera_id
        self.org_id = org_id
        self.history = TrackHistory(TRAIL_LENGTH, STOP_THRESHOLD, STOP_TIME)
        self.counter = LineCounter(lines)
        self.lines = lines

        self.events = EventLogger(camera_id=camera_id, org_id=org_id)
        self.database = self.events.database

        self.memory = AgentMemory()

        sampler = LearningSampler(
            LOW_CONFIDENCE_THRESHOLD,
            INTERMEDIATE_CONFIDENCE_THRESHOLD,
            MIN_LEARNING_INTERVAL,
            MAX_LEARNING_CASES,
        )
        collector = CaseCollector(sampler, events=self.events) if LEARNING_ENABLED else None

        self.agent = TrafficAgent(self.events, self.memory, collector, LOW_CONFIDENCE_THRESHOLD)

        self.seen_ids = set()
        self.statuses = {}

        # Janela deslizante de veículos únicos vistos pela primeira vez nos
        # últimos ROLLING_WINDOW_SECONDS segundos, para suavizar as contagens
        # por classe exibidas ao vivo (evita que oclusões de 1 frame façam o
        # número "piscar").
        self.recent_sightings = deque()

        self.last_snapshot = {
            "objects": 0,
            "visible": {},
            "visible_recent": {},
            "rolling_window_seconds": ROLLING_WINDOW_SECONDS,
            "stopped": 0,
            "flow_per_minute": 0,
            "congestion": {"level": "aguardando", "score": 0},
            "agent": self.agent.explanation(),
            "entries": 0,
            "exits": 0,
            "model_version": MODEL_VERSION,
        }

    def process(self, frame):
        result = self.model.track(
            frame, persist=True, tracker=TRACKER, conf=CONFIDENCE, verbose=False, imgsz=INFERENCE_IMGSZ
        )[0]

        visible = Counter()
        stopped = 0
        detections = []

        if result.boxes is not None and result.boxes.id is not None:
            boxes = result.boxes.xyxy.cpu().numpy().astype(int)
            ids = result.boxes.id.int().cpu().tolist()
            classes = result.boxes.cls.int().cpu().tolist()
            confidences = result.boxes.conf.cpu().tolist()

            for box, track_id, class_id, confidence in zip(boxes, ids, classes, confidences):
                track_id = int(track_id)
                class_id = int(class_id)
                confidence = float(confidence)
                name = str(result.names[class_id])
                x1, y1, x2, y2 = int(box[0]), int(box[1]), int(box[2]), int(box[3])
                center = (int((x1 + x2) // 2), int((y1 + y2) // 2))

                status = self.history.update(track_id, center)
                crossing = self.counter.update(track_id, name, center)

                detection = {
                    "frame_id": int(result.path) if str(result.path).isdigit() else None,
                    "track_id": track_id,
                    "class_id": class_id,
                    "class_name": name,
                    "confidence": round(confidence, 4),
                    "bbox": [x1, y1, x2, y2],
                    "center": [center[0], center[1]],
                    "status": str(status),
                    "model_version": str(MODEL_VERSION),
                }
                detections.append(detection)

                if hasattr(self.database, "record_detection"):
                    self.database.record_detection(detection, frame.shape, org_id=self.org_id)
                    self.database.record_track(detection, org_id=self.org_id)

                if track_id not in self.seen_ids:
                    self.seen_ids.add(track_id)
                    self.recent_sightings.append((time.monotonic(), name, track_id))
                    self.events.emit("VEHICLE_DETECTED", **detection)
                    self.events.emit("VEHICLE_ENTERED", **detection)

                if crossing:
                    self.events.emit("VEHICLE_EXITED", line=str(crossing), **detection)

                if self.statuses.get(track_id) != status:
                    self.statuses[track_id] = status
                    self.events.emit("VEHICLE_STOPPED" if status == "PARADO" else "VEHICLE_MOVING", **detection)

                visible[name] += 1
                if status == "PARADO":
                    stopped += 1

                self._draw_detection(frame, detection)

        flow_per_minute = self.counter.flow_per_minute()
        congestion = calculate_congestion(
            sum(visible.values()),
            stopped_vehicles=stopped,
            flow_per_minute=flow_per_minute,
        )

        for detection in detections:
            observation = dict(detection)
            observation["status"] = self.statuses.get(detection["track_id"], "DESCONHECIDO")
            self.agent.observe(frame, observation, congestion)

        cutoff = time.monotonic() - ROLLING_WINDOW_SECONDS
        while self.recent_sightings and self.recent_sightings[0][0] < cutoff:
            self.recent_sightings.popleft()
        visible_recent = Counter(name for _, name, _ in self.recent_sightings)

        self.last_snapshot = {
            "objects": int(sum(visible.values())),
            "visible": {str(name): int(count) for name, count in visible.items()},
            "visible_recent": {str(name): int(count) for name, count in visible_recent.items()},
            "rolling_window_seconds": ROLLING_WINDOW_SECONDS,
            "stopped": int(stopped),
            "flow_per_minute": int(flow_per_minute),
            "congestion": {
                str(key): (float(value) if isinstance(value, (np.floating,)) else value)
                for key, value in congestion.items()
            },
            "agent": str(self.agent.explanation()),
            "entries": int(self.counter.totals["entrada"]),
            "exits": int(self.counter.totals["saida"]),
            "model_version": str(MODEL_VERSION),
        }

        return frame

    def _draw_detection(self, frame, detection):
        x1, y1, x2, y2 = detection["bbox"]
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
        cv2.putText(
            frame,
            f"{detection['class_name']} #{detection['track_id']}",
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 0),
            2,
        )
        trail = self.history.trail(detection["track_id"])
        if len(trail) > 1:
            cv2.polylines(frame, [np.array(trail, dtype=np.int32)], False, (0, 180, 255), 2)


def run_source(model, source, window_name="Camera Inteligente de Transito"):
    capture = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    if not capture.isOpened():
        raise RuntimeError(f"Nao foi possivel abrir a fonte: {source}")

    processor = TrafficProcessor(model)

    while True:
        ok, frame = capture.read()
        if not ok:
            break

        processed_frame = processor.process(frame)
        cv2.imshow(window_name, processed_frame)

        if cv2.waitKey(1) & 0xFF in (27, ord("q")):
            break

    capture.release()
    cv2.destroyAllWindows()
