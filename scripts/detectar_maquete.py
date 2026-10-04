"""Versão para a câmera zenital da maquete; ajuste config/config.py antes de usar."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import CAMERA_ID, MODEL_PATH, ZONES
from utils.pipeline import run_source


def main():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modelo treinado não encontrado: {MODEL_PATH}")
    print("Zonas configuradas (valores de exemplo; calibre para a maquete):", ZONES)
    from ultralytics import YOLO
    run_source(YOLO(str(MODEL_PATH)), CAMERA_ID, "Maquete - Camera Inteligente")


if __name__ == "__main__":
    main()
