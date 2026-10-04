"""Orquestra o chatbot: pergunta em linguagem natural -> intenção (regras
locais) -> dados reais (query_engine) -> resposta em português (provider).

A IA nunca calcula números: o parser resolve datas/horários/câmera a partir
do texto, o query_engine consulta o Postgres/JSONL, e o provider só formata
o resultado já pronto. Isso garante que a mesma pergunta sempre produz os
mesmos números vistos no relatório em PDF.

Numa conversa, o que a pergunta não diz (período, horário, câmera) é herdado
da pergunta anterior, então perguntas de acompanhamento funcionam
("e as ocorrências?", "e de manhã?").
"""

import os
import re
import unicodedata
from datetime import date, time

from .nlu.parser import _DATE_RE, _HOUR_RANGE_RE, parse
from .providers.factory import get_provider
from .query_engine import QueryFilters, compare_periods, compute_summary, get_occurrences


# ---- triagem: só pergunta de DADOS consulta dados -------------------------------------
# Sem isso, qualquer frase ("o via é um bom app?") caía no padrão "resumo de hoje" e recebia
# números que nada têm a ver com a pergunta.

_DATA_WORDS = (
    "veicul", "carro", "moto", "onibus", "caminh", "pessoa", "pedestre", "fluxo", "transito", "trafego",
    "pico", "movimento", "movimentad", "congestion", "engarraf", "retenc", "ocorrenc", "parado", "acident",
    "alagament", "camera", "cam_", "contagem", "quantos", "quantas", "total", "media", "compar", "relatorio",
    "periodo", "hoje", "ontem", "anteontem", "semana", "madrugada", "manha", "tarde", "noite", "horario",
    "detec", "circul", "passaram", "passou", "entrada", "saida", "velocidade", "lotad", "intens",
)
_GREETING_RE = re.compile(r"^(oi+|ola|opa|hey|e ai|bom dia|boa tarde|boa noite)\b[\s,!.?]*")
_THANKS_RE = re.compile(r"\b(obrigad|valeu|thanks|brigad)")

SCOPE_REPLIES = {
    "greeting": "Olá! Sou a VIA. Pergunte sobre o fluxo, os horários de pico ou as ocorrências das suas câmeras.",
    "thanks": "Por nada! Se quiser, posso consultar outro período ou outra câmera.",
    "out_of_scope": (
        "Eu respondo perguntas sobre os dados de trânsito das suas câmeras: fluxo, horários de pico, tipos de "
        "veículo, ocorrências e comparações entre períodos. Por exemplo: “Qual foi o horário de pico hoje?”"
    ),
}


def _norm(text):
    return unicodedata.normalize("NFKD", str(text).lower()).encode("ascii", "ignore").decode()


def triage(question):
    """'data' | 'greeting' | 'thanks' | 'out_of_scope'."""
    text = _norm(question).strip()
    greeting = _GREETING_RE.match(text)
    rest = text[greeting.end():] if greeting else text  # "boa tarde" não é "tarde" do dia
    if _DATE_RE.search(rest) or _HOUR_RANGE_RE.search(rest) or any(word in rest for word in _DATA_WORDS):
        return "data"
    if greeting:
        return "greeting"
    if _THANKS_RE.search(text):
        return "thanks"
    return "out_of_scope"


def is_data_question(question):
    return triage(question) == "data"


def _known_cameras(org_id=None):
    if os.getenv("DATABASE_BACKEND", "").strip().lower() != "postgres":
        return []
    from data.postgres import create_database

    return create_database().list_cameras(org_id=org_id)


def restore_intent(previous):
    """Volta o `intent` serializado (JSON) de uma resposta anterior. None se inválido."""
    if not isinstance(previous, dict):
        return None
    try:
        return {
            "date_from": date.fromisoformat(previous["date_from"]),
            "date_to": date.fromisoformat(previous["date_to"]),
            "hour_from": time.fromisoformat(previous["hour_from"]) if previous.get("hour_from") else None,
            "hour_to": time.fromisoformat(previous["hour_to"]) if previous.get("hour_to") else None,
            "camera_key": previous.get("camera_key") or None,
        }
    except (KeyError, TypeError, ValueError):
        return None


def answer_question(question, org_id=None, previous_intent=None):
    kind = triage(question)
    if kind != "data":
        # Sem consulta, sem custo, sem inventar número: só orienta o que dá para perguntar.
        return {"answer": SCOPE_REPLIES[kind], "data": {"has_data": False}, "intent": None, "provider": "escopo"}

    known_cameras = _known_cameras(org_id)
    intent = parse(question, known_cameras)

    prior = restore_intent(previous_intent)
    if prior:
        if not intent.date_explicit:
            intent.date_from, intent.date_to = prior["date_from"], prior["date_to"]
        if not intent.hour_explicit:
            intent.hour_from, intent.hour_to = prior["hour_from"], prior["hour_to"]
        if not intent.camera_explicit:
            intent.camera_key = prior["camera_key"]

    filters = QueryFilters(
        date_from=intent.date_from,
        date_to=intent.date_to,
        hour_from=intent.hour_from,
        hour_to=intent.hour_to,
        camera_key=intent.camera_key,
        org_id=org_id,
    )

    if intent.metric == "occurrences":
        data = get_occurrences(filters)
    elif intent.metric == "compare" and intent.compare_hour_from and intent.hour_from:
        filters_b = QueryFilters(
            date_from=intent.date_from,
            date_to=intent.date_to,
            hour_from=intent.compare_hour_from,
            hour_to=intent.compare_hour_to,
            camera_key=intent.camera_key,
            org_id=org_id,
        )
        data = compare_periods(filters, filters_b)
    else:
        data = compute_summary(filters)

    provider = get_provider()
    answer = provider.explain(question, data)

    return {
        "answer": answer,
        "data": data,
        "intent": {
            "metric": intent.metric,
            "date_from": intent.date_from.isoformat(),
            "date_to": intent.date_to.isoformat(),
            "hour_from": intent.hour_from.isoformat() if intent.hour_from else None,
            "hour_to": intent.hour_to.isoformat() if intent.hour_to else None,
            "camera_key": intent.camera_key,
            "confidence": intent.confidence,
        },
        "provider": provider.name,
    }
