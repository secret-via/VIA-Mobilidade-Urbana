import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from learning.model_manager import ModelManager
from traffic.events import EventLogger


def main():
    parser = argparse.ArgumentParser(description="Promove somente candidato que relatório marcou como aprovado.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    manager = ModelManager(ROOT, EventLogger())
    if report["decision"]["approved"]:
        print("Promovido:", manager.promote(args.candidate, args.version, report["candidate"]))
    else:
        print("Rejeitado:", manager.reject(args.candidate, args.version, report["candidate"]))


if __name__ == "__main__": main()
