import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from learning.model_manager import ModelManager
from traffic.events import EventLogger


def main():
    parser = argparse.ArgumentParser(description="Restaura uma versão arquivada como produção.")
    parser.add_argument("--model", type=Path, required=True, help="Peso .pt em models/archive")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    print(ModelManager(ROOT, EventLogger()).rollback(args.model, args.version))


if __name__ == "__main__": main()
