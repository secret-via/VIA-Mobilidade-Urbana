"""Eventos estruturados persistidos em JSON Lines e PostgreSQL."""

import json
from datetime import datetime, timezone
from pathlib import Path

from data.postgres import create_database


def _json_default(value):
    """Converte escalares NumPy/PyTorch para tipos JSON."""
    if hasattr(value, "item"):
        return value.item()

    if hasattr(value, "tolist"):
        return value.tolist()

    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


class EventLogger:
    def __init__(self, path=None, camera_id=None, org_id=None):
        root = Path(__file__).resolve().parents[1]

        self.path = Path(
            path or root / "logs" / "events.jsonl"
        )

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.camera_id = camera_id
        self.org_id = org_id
        self.database = create_database()

    def emit(self, event_type, **data):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "camera_id": self.camera_id,
            "org_id": self.org_id,
            **data,
        }

        # JSON Lines continua sendo mantido como histórico local.
        with self.path.open("a", encoding="utf-8") as output:
            output.write(
                json.dumps(
                    event,
                    ensure_ascii=False,
                    default=_json_default,
                )
                + "\n"
            )

        # PostgreSQL recebe o mesmo evento quando configurado.
        self.database.record_event(event)

        return event