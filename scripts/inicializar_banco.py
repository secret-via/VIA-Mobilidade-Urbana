"""Cria e prepara as tabelas do sistema."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.postgres import create_database


def main():
    database = create_database()

    if not hasattr(database, "initialize"):
        print("PostgreSQL não está configurado.")
        return

    print("Criando tabelas...")
    database.initialize()

    print("Inserindo classes...")
    database.seed_classes()

    print()
    print("Banco inicializado com sucesso!")
    print("Tabelas e classes estão prontas.")


if __name__ == "__main__":
    main()