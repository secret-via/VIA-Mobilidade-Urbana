import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import DATA_YAML, RUNS_DIR


def main():
    parser = argparse.ArgumentParser(description="Treina YOLO26 no dataset de trânsito.")
    parser.add_argument("--device", default="cpu", help="cpu, 0 ou outro dispositivo suportado pelo PyTorch")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    args = parser.parse_args()
    if not DATA_YAML.exists():
        raise FileNotFoundError(f"Dataset YAML não encontrado: {DATA_YAML}")
    from ultralytics import YOLO
    model = YOLO("yolo26n.pt")
    model.train(data=str(DATA_YAML), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                device=args.device, project=str(RUNS_DIR), name="transito", exist_ok=True)
    metrics = model.val(data=str(DATA_YAML), device=args.device)
    best = RUNS_DIR / "transito" / "weights" / "best.pt"
    print(f"Validação concluída: {metrics}")
    print(f"Melhor modelo: {best}")


if __name__ == "__main__":
    main()
