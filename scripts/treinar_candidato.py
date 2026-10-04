import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import MODEL_VERSION
from traffic.events import EventLogger


def main():
    parser = argparse.ArgumentParser(description="Treina candidato; não altera produção.")
    parser.add_argument("--data", type=Path, required=True, help="data.yaml da versão do dataset")
    parser.add_argument("--version", default="v002")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--epochs", type=int, default=100)
    args = parser.parse_args()
    if not args.data.exists(): raise FileNotFoundError(args.data)
    events = EventLogger(); events.emit("MODEL_TRAINING_STARTED", version=args.version, dataset=str(args.data))
    from ultralytics import YOLO
    model = YOLO("yolo26n.pt")
    run = ROOT / "runs" / f"candidate_{args.version}"
    model.train(data=str(args.data), epochs=args.epochs, device=args.device, project=str(ROOT / "runs"), name=run.name, exist_ok=True)
    candidate = ROOT / "models" / "candidates" / f"candidate_{args.version}.pt"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(run / "weights" / "best.pt", candidate)
    events.emit("MODEL_TRAINING_FINISHED", version=args.version, candidate=str(candidate), previous_version=MODEL_VERSION)
    print(candidate)


if __name__ == "__main__": main()
