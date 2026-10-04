import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.config import DATA_YAML, MIN_MODEL_IMPROVEMENT, MODEL_PATH
from learning.evaluator import compare, metrics_from_ultralytics, save_report


def main():
    parser = argparse.ArgumentParser(description="Compara candidato com produção sem promovê-lo.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--current", type=Path, default=MODEL_PATH)
    parser.add_argument("--data", type=Path, default=DATA_YAML)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    current = metrics_from_ultralytics(args.current, args.data, args.device)
    candidate = metrics_from_ultralytics(args.candidate, args.data, args.device)
    decision = compare(current, candidate, MIN_MODEL_IMPROVEMENT)
    report = ROOT / "logs" / f"evaluation_{args.candidate.stem}.json"
    save_report(report, current, candidate, decision)
    print(f"{'APROVADO' if decision['approved'] else 'REJEITADO'}: melhoria mAP={decision['improvement']:+.4f}; relatório: {report}")


if __name__ == "__main__": main()
