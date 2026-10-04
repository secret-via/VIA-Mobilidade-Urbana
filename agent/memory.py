import json
from datetime import datetime, timezone
from pathlib import Path


class AgentMemory:
    def __init__(self, path=None):
        root = Path(__file__).resolve().parents[1]
        self.path = Path(path or root / "data" / "memory" / "memory.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def remember(self, kind, **data):
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "type": kind, **data}
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, default=lambda value: value.item() if hasattr(value, "item") else value.tolist()) + "\n")
        return record

    def recent(self, limit=20):
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines]
