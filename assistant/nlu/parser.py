"""Extração de intenção 100% por regras/regex, sem depender de nenhuma IA
generativa. Cobre os exemplos de pergunta do pedido original (data, horário,
intervalo de horário, período do dia, câmera/local, comparação de períodos,
ocorrências) e funciona mesmo com AI_PROVIDER=none.
"""

import re
from datetime import date, datetime, time, timedelta

from config.config import BR_TIMEZONE

from .schema import QueryIntent

_HOUR_RANGE_RE = re.compile(
    r"(\d{1,2})\s*h(?:oras)?\s*(?:[àa]s|a|-|e|at[ée])\s*(\d{1,2})\s*h(?:oras)?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")

_PERIOD_HOURS = {
    # (hora_inicial, hora_final) - hora_final=0 significa "até a meia-noite"
    # e é tratado como intervalo que cruza o dia por quem consome isso
    # (ver aggregate_vehicle_events/hour_range em dashboard/app.py).
    "madrugada": (0, 6),
    "manhã": (6, 12),
    "manha": (6, 12),
    "tarde": (12, 18),
    "noite": (18, 0),
}

_METRIC_KEYWORDS = {
    "compare": ("compar", " versus ", " vs "),
    "occurrences": ("ocorrênc", "ocorrenc", "congestionamento", "acidente", "alagamento"),
}


def _resolve_relative_date(text_lower, today):
    if "anteontem" in text_lower:
        day = today - timedelta(days=2)
        return day, day
    if "ontem" in text_lower:
        day = today - timedelta(days=1)
        return day, day
    if "hoje" in text_lower:
        return today, today
    if any(term in text_lower for term in ("essa semana", "esta semana", "última semana", "ultima semana")):
        return today - timedelta(days=6), today
    if "semana passada" in text_lower:
        return today - timedelta(days=13), today - timedelta(days=7)
    if any(term in text_lower for term in ("esse mês", "este mês", "esse mes", "este mes")):
        return today.replace(day=1), today
    return None


def _resolve_explicit_dates(text, today):
    matches = _DATE_RE.findall(text)
    if not matches:
        return None

    parsed = []
    for day_s, month_s, year_s in matches:
        try:
            year = int(year_s) if year_s else today.year
            if year < 100:
                year += 2000
            parsed.append(date(year, int(month_s), int(day_s)))
        except ValueError:
            continue

    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0], parsed[0]
    return min(parsed), max(parsed)


def _resolve_hour_ranges(text):
    ranges = []
    for start, end in _HOUR_RANGE_RE.findall(text):
        start_hour, end_hour = int(start) % 24, int(end) % 24
        ranges.append((start_hour, end_hour))
    return ranges


def _resolve_period_of_day(text_lower):
    for period, hours in _PERIOD_HOURS.items():
        if period in text_lower:
            return hours
    return None


def _resolve_camera(text_lower, known_cameras):
    for camera in known_cameras:
        for candidate in filter(None, [
            camera.get("name"), camera.get("camera_key"), camera.get("location_label"),
        ]):
            if candidate.lower() in text_lower:
                return camera.get("camera_key")
    return None


def _resolve_metric(text_lower):
    for metric, keywords in _METRIC_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return metric
    return "flow"


def parse(text, known_cameras=None, today=None):
    known_cameras = known_cameras or []
    today = today or datetime.now(BR_TIMEZONE).date()
    text_lower = text.lower()

    confidence = 0.3

    date_range = _resolve_relative_date(text_lower, today) or _resolve_explicit_dates(text, today)
    if date_range:
        confidence += 0.35
        date_from, date_to = date_range
    else:
        date_from, date_to = today, today

    hour_from = hour_to = compare_hour_from = compare_hour_to = None
    hour_ranges = _resolve_hour_ranges(text)
    if hour_ranges:
        confidence += 0.2
        hour_from, hour_to = time(hour_ranges[0][0]), time(hour_ranges[0][1])
        if len(hour_ranges) > 1:
            compare_hour_from, compare_hour_to = time(hour_ranges[1][0]), time(hour_ranges[1][1])
    else:
        period = _resolve_period_of_day(text_lower)
        if period:
            confidence += 0.15
            hour_from, hour_to = time(period[0]), time(period[1])

    camera_key = _resolve_camera(text_lower, known_cameras)
    if camera_key:
        confidence += 0.15

    metric = _resolve_metric(text_lower)

    return QueryIntent(
        metric=metric,
        date_from=date_from,
        date_to=date_to,
        hour_from=hour_from,
        hour_to=hour_to,
        camera_key=camera_key,
        compare_hour_from=compare_hour_from,
        compare_hour_to=compare_hour_to,
        confidence=min(confidence, 1.0),
        raw_text=text,
        date_explicit=bool(date_range),
        hour_explicit=hour_from is not None,
        camera_explicit=bool(camera_key),
    )
