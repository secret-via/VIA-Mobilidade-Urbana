import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


class DatasetManager:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[1])
        self.queue = self.root / "data" / "learning_queue" / "approved"

    def create_version(self):
        versions = sorted((self.root / "data").glob("dataset_v[0-9][0-9][0-9]"))
        number = int(versions[-1].name[-3:]) + 1 if versions else 1
        target = self.root / "data" / f"dataset_v{number:03d}"
        shutil.copytree(self.root / "data" / "images", target / "images")
        shutil.copytree(self.root / "data" / "labels", target / "labels")
        shutil.copy2(self.root / "data" / "data.yaml", target / "data.yaml")
        added = 0
        for metadata_file in self.queue.glob("*.json"):
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            label = metadata.get("confirmed_label")
            bbox = metadata.get("bbox_yolo")
            image = metadata_file.with_name(metadata["image"])
            if label is None or not bbox or not image.exists():
                continue
            destination = target / "images" / "train" / image.name
            shutil.copy2(image, destination)
            (target / "labels" / "train" / image.with_suffix(".txt").name).write_text(
                f"{label} {' '.join(map(str, bbox))}\n", encoding="utf-8")
            added += 1
        manifest = {"version": target.name, "created_at": datetime.now(timezone.utc).isoformat(), "approved_added": added,
                    "source_dataset_preserved": True}
        train_images = sorted((target / "images" / "train").glob("*.*"))
        val_images = sorted((target / "images" / "val").glob("*.*"))
        (target / "train.txt").write_text("\n".join(str(item.resolve()) for item in train_images) + "\n", encoding="utf-8")
        (target / "val.txt").write_text("\n".join(str(item.resolve()) for item in val_images) + "\n", encoding="utf-8")
        (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return target, manifest
