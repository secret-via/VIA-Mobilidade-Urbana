"""Planos comerciais da VIA e seus limites.

Fonte única dos limites aplicados pelo app. Os nomes seguem o briefing
(Report, Insight, Intelligence, Business). Os NÚMEROS abaixo são valores
iniciais de trabalho, não preços nem contrato: ajuste aqui conforme o ticket
e o custo real de processamento forem validados. `None` significa ilimitado.

Não há cobrança automática por enquanto: as organizações são criadas pela VIA
(painel /admin) depois do orçamento fechado.
"""

# assistant: chat VIA | pdf: relatórios exportados (o detalhe completo só existe no PDF)
ALL_FEATURES = frozenset({"assistant", "pdf"})

PLANS = {
    # Organização da própria VIA (demonstração, operação interna).
    "interno": {
        "label": "Interno VIA",
        "max_users": None,
        "max_cameras": None,
        "pdf_per_month": None,
        "chat_per_month": None,
        "features": ALL_FEATURES,
    },
    # Estudo pontual: coleta, análise e relatório final.
    "report": {
        "label": "VIA Report",
        "max_users": 2,
        "max_cameras": 2,
        "pdf_per_month": 3,
        "chat_per_month": 0,
        "features": frozenset({"pdf"}),
    },
    # Estudo aprofundado: mais pontos, comparativos e visualizações avançadas.
    "insight": {
        "label": "VIA Insight",
        "max_users": 3,
        "max_cameras": 5,
        "pdf_per_month": 10,
        "chat_per_month": 0,
        "features": frozenset({"pdf"}),
    },
    # Plataforma recorrente para profissionais/equipes.
    "intelligence": {
        "label": "VIA Intelligence",
        "max_users": 5,
        "max_cameras": 10,
        "pdf_per_month": 30,
        "chat_per_month": 300,
        "features": ALL_FEATURES,
    },
    # Empresas de engenharia e organizações de maior volume.
    "business": {
        "label": "VIA Business",
        "max_users": 25,
        "max_cameras": 50,
        "pdf_per_month": 200,
        "chat_per_month": 3000,
        "features": ALL_FEATURES,
    },
}

DEFAULT_PLAN = "intelligence"

ROLE_VIA_ADMIN = "via_admin"  # equipe VIA: enxerga e administra todas as organizações
ROLE_OWNER = "owner"          # responsável da organização: gerencia usuários dela
ROLE_MEMBER = "member"        # usuário comum
ROLES = (ROLE_VIA_ADMIN, ROLE_OWNER, ROLE_MEMBER)

INTERNAL_ORG_NAME = "VIA (interno)"


def get_plan(plan_key):
    return PLANS.get(plan_key) or PLANS[DEFAULT_PLAN]


def plan_allows(plan_key, feature):
    return feature in get_plan(plan_key)["features"]


def within_limit(limit, current):
    """True se ainda cabe mais um item. `limit=None` é ilimitado."""
    return limit is None or current < limit
