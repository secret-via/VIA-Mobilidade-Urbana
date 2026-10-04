import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


class ModelManager:
    def __init__(self, root=None, events=None):
        base = Path(root or Path(__file__).resolve().parents[1]) / "models"
        self.production, self.candidates, self.archive = base / "production", base / "candidates", base / "archive"
        for folder in (self.production, self.candidates, self.archive): folder.mkdir(parents=True, exist_ok=True)
        self.events = events

    def promote(self, candidate, version, metrics):
        candidate, target = Path(candidate), self.production / f"{version}.pt"
        current = next(self.production.glob("*.pt"), None)
        if current: shutil.move(str(current), str(self.archive / current.name))
        shutil.copy2(candidate, target)
        self._record(version, "approved", metrics)
        if self.events: self.events.emit("MODEL_APPROVED", version=version, model=str(target), metrics=metrics)
        return target

    def reject(self, candidate, version, metrics):
        candidate = Path(candidate)
        rejected = self.archive / f"rejected_{version}.pt"
        shutil.copy2(candidate, rejected)
        self._record(version, "rejected", metrics)
        if self.events: self.events.emit("MODEL_REJECTED", version=version, model=str(candidate), metrics=metrics)
        return rejected

    def rollback(self, archived_model, version, metrics=None):
        """Restaura explicitamente um peso arquivado sem apagar o modelo atual."""
        archived_model = Path(archived_model)
        if not archived_model.exists():
            raise FileNotFoundError(archived_model)
        current = next(self.production.glob("*.pt"), None)
        if current:
            shutil.move(str(current), str(self.archive / current.name))
        restored = self.production / f"{version}.pt"
        shutil.copy2(archived_model, restored)
        self._record(version, "rollback", metrics or {})
        if self.events: self.events.emit("MODEL_APPROVED", action="rollback", version=version, model=str(restored))
        return restored

    def _record(self, version, status, metrics):
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "version": version, "status": status, "metrics": metrics}
        with (self.production.parent / "history.jsonl").open("a", encoding="utf-8") as output: output.write(json.dumps(record) + "\n")
