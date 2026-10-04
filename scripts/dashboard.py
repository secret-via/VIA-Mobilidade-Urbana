"""Inicia o dashboard local com vídeo, API e WebSocket."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import CAMERA_ID, MODEL_PATH
from dashboard.app import create_app


def main():
    parser = argparse.ArgumentParser(description="Dashboard web da Câmera Inteligente de Trânsito.")
    parser.add_argument("--camera", type=int, default=CAMERA_ID)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 local; 0.0.0.0 libera na rede local")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    if not args.model.exists():
        raise FileNotFoundError(f"Modelo não encontrado: {args.model}. Treine antes de abrir o dashboard.")
    app, _service = create_app(args.model, args.camera)
    print(f"Dashboard: http://{args.host}:{args.port}")
    print("Pressione Ctrl+C para encerrar.")
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
