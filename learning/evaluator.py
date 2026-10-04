import json
from pathlib import Path


def metrics_from_ultralytics(model_path, data_yaml, device="cpu"):
    from ultralytics import YOLO
    metrics = YOLO(str(model_path)).val(data=str(data_yaml), device=device, verbose=False)
    return {"precision": float(metrics.box.mp), "recall": float(metrics.box.mr), "map50": float(metrics.box.map50),
            "map50_95": float(metrics.box.map)}


def compare(current, candidate, minimum_improvement=0.01):
    delta = candidate["map50_95"] - current["map50_95"]
    return {"approved": delta >= minimum_improvement, "improvement": round(delta, 6),
            "reason": "candidate_improved" if delta >= minimum_improvement else "insufficient_improvement"}


def save_report(path, current, candidate, decision):
    report = {"current": current, "candidate": candidate, "decision": decision}
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
