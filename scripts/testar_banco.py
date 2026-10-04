"""Testa a conexão do projeto com PostgreSQL."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.postgres import create_database


def main():
    database = create_database()

    if not hasattr(database, "test_connection"):
        print("PostgreSQL não está configurado.")
        return

    result = database.test_connection()

    print("PostgreSQL conectado com sucesso!")
    print(f"Banco: {result[0]}")
    print(f"Servidor: {result[1]}")


if __name__ == "__main__":
    main()