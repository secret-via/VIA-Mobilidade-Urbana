"""Fallback sem nenhuma IA generativa: monta a resposta por template
determinístico a partir do JSON do query_engine. Garante que o assistente
sempre responde, mesmo sem nenhum provedor de IA configurado/disponível.
"""

from datetime import datetime

from config.config import BR_TIMEZONE

from .base import LLMProvider


def _br_date(iso):
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _format_period(data):
    filters = data.get("filters", {})
    date_from, date_to = filters.get("date_from"), filters.get("date_to")
    if date_from == date_to:
        period = f"em {_br_date(date_from)}"
    else:
        period = f"entre {_br_date(date_from)} e {_br_date(date_to)}"
    if filters.get("hour_from") and filters.get("hour_to"):
        period += f", das {filters['hour_from'][:5]} às {filters['hour_to'][:5]}"
    return period


def _format_summary(data):
    if not data.get("has_data"):
        if data.get("source") == "none":
            return (
                "Não há um banco de dados configurado no momento, então não tenho histórico "
                "para consultar. Configure o PostgreSQL (DATABASE_BACKEND=postgres) para habilitar "
                "esta análise."
            )
        return f"Não encontrei dados suficientes {_format_period(data)} para responder isso."

    total = data["total_vehicles"]
    by_class = data.get("by_class") or {}
    breakdown = ", ".join(f"{count} {name}" for name, count in sorted(by_class.items(), key=lambda kv: -kv[1]))
    peak = data.get("peak_bucket")
    peak_text = ""
    if peak:
        try:
            hour = datetime.fromisoformat(peak["timestamp"]).astimezone(BR_TIMEZONE).strftime("%d/%m %H:%M")
        except ValueError:
            hour = peak["timestamp"]
        peak_text = f" O pico foi às {hour}, com {peak['total']} veículos."

    breakdown_text = f" ({breakdown})" if breakdown else ""
    period = _format_period(data)

    camera_text = ""
    by_camera = data.get("by_camera") or {}
    if len(by_camera) > 1:
        camera_totals = {camera: sum(classes.values()) for camera, classes in by_camera.items()}
        top_camera = max(camera_totals, key=camera_totals.get)
        camera_text = f" A câmera com maior fluxo foi {top_camera}, com {camera_totals[top_camera]} veículos."

    return (
        f"{period[0].upper()}{period[1:]}, foram registrados {total} veículos{breakdown_text}."
        f"{peak_text}{camera_text}"
    )


def _format_compare(data):
    if not data.get("has_data"):
        return "Não encontrei dados suficientes em nenhum dos dois períodos para comparar."

    period_a, period_b = data["period_a"], data["period_b"]
    delta = data["delta_total"]
    direction = "a mais" if delta > 0 else ("a menos" if delta < 0 else "igual")
    return (
        f"No período A ({_format_period(period_a)}) foram {period_a['total_vehicles']} veículos; "
        f"no período B ({_format_period(period_b)}) foram {period_b['total_vehicles']} veículos "
        f"({abs(delta)} veículos {direction})."
    )


def _format_occurrences(data):
    if not data.get("has_data"):
        return f"Não há ocorrências registradas {_format_period(data)}."

    # Nomes em português (a tela não mostra códigos internos como CONGESTION_STARTED).
    labels = {
        "CONGESTION_STARTED": ("congestionamento iniciado", "congestionamentos iniciados"),
        "CONGESTION_ENDED": ("congestionamento encerrado", "congestionamentos encerrados"),
        "VEHICLE_STOPPED": ("veículo parado", "veículos parados"),
    }
    counts = {}
    for event in data["events"]:
        event_type = event.get("type", "desconhecido")
        counts[event_type] = counts.get(event_type, 0) + 1

    def _name(event_type, count):
        singular, plural = labels.get(event_type, ("ocorrência de outro tipo", "ocorrências de outros tipos"))
        return singular if count == 1 else plural

    breakdown = ", ".join(f"{count} {_name(name, count)}" for name, count in counts.items())
    return f"Foram registradas {len(data['events'])} ocorrências {_format_period(data)}: {breakdown}."


class NullProvider(LLMProvider):
    name = "none"

    def available(self):
        return True

    def explain(self, question, data):
        if "period_a" in data:
            return _format_compare(data)
        if "events" in data:
            return _format_occurrences(data)
        return _format_summary(data)
