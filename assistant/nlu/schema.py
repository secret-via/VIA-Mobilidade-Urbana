"""Contrato de intenção extraída de uma pergunta em linguagem natural."""

from dataclasses import dataclass
from datetime import date, time
from typing import Optional


@dataclass
class QueryIntent:
    metric: str  # "flow" | "compare" | "occurrences"
    date_from: date
    date_to: date
    hour_from: Optional[time] = None
    hour_to: Optional[time] = None
    camera_key: Optional[str] = None
    compare_hour_from: Optional[time] = None
    compare_hour_to: Optional[time] = None
    confidence: float = 0.3
    raw_text: str = ""
    # O que a pergunta disse de fato (o resto é padrão). Numa conversa, o que não foi
    # dito é herdado da pergunta anterior ("e as ocorrências?" mantém período e câmera).
    date_explicit: bool = False
    hour_explicit: bool = False
    camera_explicit: bool = False
