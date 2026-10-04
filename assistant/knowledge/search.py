"""Busca na base de conhecimento (sem IA generativa): pontua cada artigo pelas
frases-chave presentes na pergunta e devolve os melhores."""

import re
import unicodedata

from .articles import ARTICLES

_BY_ID = {article.id: article for article in ARTICLES}

HELP_LEADS = (
    "como ", "o que ", "oque ", "por que ", "porque ", "por quê ", "onde ", "quem ", "posso ", "consigo ", "tem como",
    "da para", "preciso ", "quero ", "qual e o limite", "quais sao", "quais as", "pra que", "para que",
)


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text).lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9_/ ]", " ", text)).strip()


def starts_like_help(normalized):
    padded = normalized + " "
    return any(padded.startswith(lead) for lead in HELP_LEADS)


def search(question, limit=3):
    """[(artigo, pontuação)] ordenado, só com pontuação > 0."""
    text = " " + normalize(question) + " "
    scored = []
    for article in ARTICLES:
        score = sum(weight for phrase, weight in article.keywords if phrase in text)
        if score > 0:
            scored.append((article, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:limit]


def best(question):
    hits = search(question, 1)
    return hits[0] if hits else (None, 0.0)


def render(article, account=None):
    return article.answer(account) if callable(article.answer) else article.answer


def get(article_id):
    return _BY_ID[article_id]
