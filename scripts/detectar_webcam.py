import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import CAMERA_ID, MODEL_PATH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=CAMERA_ID)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    args = parser.parse_args()
    if not args.model.exists():
        raise FileNotFoundError(f"Modelo treinado não encontrado: {args.model}. Execute scripts/treinar.py primeiro.")
    from ultralytics import YOLO
    from utils.pipeline import run_source
    run_source(YOLO(str(args.model)), args.camera)


if __name__ == "__main__":
    main()
