import json
from datetime import datetime, timezone
from pathlib import Path

from learning.sampler import LearningSampler


def _json_default(value):
    """Aceita escalares NumPy/PyTorch recebidos das detecções."""
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "tolist"):
        return value.tolist()
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


class CaseCollector:
    def __init__(self, sampler, queue_dir=None, events=None):
        root = Path(__file__).resolve().parents[1]
        self.sampler, self.events = sampler, events
        self.pending = Path(queue_dir or root / "data" / "learning_queue" / "pending")
        self.pending.mkdir(parents=True, exist_ok=True)

    def collect(self, frame, detection, reason):
        if not self.sampler.should_collect(detection):
            return None
        import cv2
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        image = self.pending / f"case_{stamp}.jpg"
        cv2.imwrite(str(image), frame)
        metadata = {"image": image.name, "reason": reason, "prediction": detection,
                    "created_at": datetime.now(timezone.utc).isoformat(), "review": None}
        image.with_suffix(".json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        if self.events:
            self.events.emit("LEARNING_CASE_CREATED", case=str(image), reason=reason, **detection)
        return image
