"""Gerencia organizações e usuários do VIA pelo terminal (PostgreSQL).

Exemplos:
    python scripts/gerenciar_contas.py criar-admin --email voce@via.com --senha 'minimo8chars'
    python scripts/gerenciar_contas.py criar-org --nome "Prefeitura de Tubarão" --plano intelligence \
        --email gestor@tubarao.sc.gov.br --senha 'minimo8chars'
    python scripts/gerenciar_contas.py listar
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from accounts.store import AccountStore
from config.config import BR_TIMEZONE
from config.plans import PLANS, ROLE_OWNER, ROLE_VIA_ADMIN
from data.postgres import PostgresDatabase


def main():
    parser = argparse.ArgumentParser(description="Contas e organizações do VIA.")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("criar-admin", help="Cria um usuário da equipe VIA (admin da plataforma).")
    admin.add_argument("--email", required=True)
    admin.add_argument("--senha", required=True)
    admin.add_argument("--nome")

    org = sub.add_parser("criar-org", help="Cria uma organização cliente e o responsável dela.")
    org.add_argument("--nome", required=True, help="Nome da organização")
    org.add_argument("--plano", choices=[key for key in PLANS if key != "interno"], default="intelligence")
    org.add_argument("--vencimento", help="AAAA-MM-DD (opcional)")
    org.add_argument("--email", required=True, help="E-mail do responsável")
    org.add_argument("--senha", required=True, help="Senha inicial do responsável")
    org.add_argument("--responsavel", help="Nome do responsável")

    sub.add_parser("listar", help="Lista organizações, uso e usuários.")

    args = parser.parse_args()

    database = PostgresDatabase()
    database.initialize()
    store = AccountStore(database)
    store.initialize()

    if args.command == "criar-admin":
        user = store.create_user(
            store.ensure_internal_org(), args.email, args.senha, role=ROLE_VIA_ADMIN, name=args.nome
        )
        print(f"Admin criado: {user['email']}")
    elif args.command == "criar-org":
        expires = None
        if args.vencimento:
            expires = datetime.fromisoformat(args.vencimento).replace(tzinfo=BR_TIMEZONE)
        org = store.create_org(args.nome, args.plano, expires)
        user = store.create_user(org["id"], args.email, args.senha, role=ROLE_OWNER, name=args.responsavel)
        print(f"Organização '{org['name']}' (plano {org['plan']}) criada. Responsável: {user['email']}")
    else:
        for org in store.list_orgs():
            print(f"[{org['id']}] {org['name']} - plano {org['plan']} - {org['status']} - "
                  f"{org['users']} usuário(s) - uso no mês: {org['usage']}")
            for user in store.list_users(org["id"]):
                state = "" if user["active"] else " (desativado)"
                print(f"      {user['email']} - {user['role']}{state}")


if __name__ == "__main__":
    main()
