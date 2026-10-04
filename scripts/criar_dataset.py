import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from learning.dataset_manager import DatasetManager

if __name__ == "__main__":
    version, manifest = DatasetManager(ROOT).create_version()
    print(f"Dataset criado: {version} | novos exemplos aprovados: {manifest['approved_added']}")
