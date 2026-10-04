"""Análises derivadas (perfil horário, mapa dia x hora, distribuição, comparação
com o período anterior etc.) calculadas a partir do MESMO resumo do
``query_engine.compute_summary``. É a fonte única dos números avançados usados
pelo painel analítico do dashboard e pelo relatório em PDF - nada aqui é
estimado: só agregações dos buckets reais de 15 minutos.
"""

import statistics
from datetime import datetime, timedelta, timezone

from assistant.query_engine import (
    QueryFilters,
    compute_summary,
    get_heatmap_data,
    get_occurrences,
)
from config.config import BR_TIMEZONE

WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
HEAVY_CLASSES = ("onibus", "caminhao")
OCCURRENCE_LABELS = {
    "CONGESTION_STARTED": "Congestionamento",
    "CONGESTION_ENDED": "Congestionamento encerrado",
    "VEHICLE_STOPPED": "Veículo parado",
}


def _local(iso):
    return datetime.fromisoformat(iso).astimezone(BR_TIMEZONE)


def _pct(part, whole):
    return round(part / whole * 100, 1) if whole else 0.0


def _histogram(values, bins=8):
    if not values:
        return []
    top = max(values)
    if top == 0:
        return [{"from": 0, "to": 0, "count": len(values)}]
    width = max(1, -(-top // bins))
    counts = [0] * bins
    for value in values:
        counts[min(bins - 1, value // width)] += 1
    return [{"from": i * width, "to": (i + 1) * width - 1, "count": counts[i]} for i in range(bins)]


def _period_days(filters):
    """Quantos dias (corridos) o período escolhido abrange."""
    if filters.since is not None:
        until = filters.until or datetime.now(timezone.utc)
        return max(1, -(-int((until - filters.since).total_seconds()) // 86400))
    return (filters.date_to - filters.date_from).days + 1


def _previous_period(filters):
    if filters.since is not None:
        until = filters.until or datetime.now(timezone.utc)
        previous_since = filters.since - (until - filters.since)
        return compute_summary(QueryFilters(
            date_from=previous_since.astimezone(BR_TIMEZONE).date(),
            date_to=filters.since.astimezone(BR_TIMEZONE).date(),
            hour_from=filters.hour_from,
            hour_to=filters.hour_to,
            camera_key=filters.camera_key,
            vehicle_type=filters.vehicle_type,
            org_id=filters.org_id,
            since=previous_since,
            until=filters.since,
        ))
    days = (filters.date_to - filters.date_from).days + 1
    previous = QueryFilters(
        date_from=filters.date_from - timedelta(days=days),
        date_to=filters.date_from - timedelta(days=1),
        hour_from=filters.hour_from,
        hour_to=filters.hour_to,
        camera_key=filters.camera_key,
        vehicle_type=filters.vehicle_type,
        org_id=filters.org_id,
    )
    return compute_summary(previous)


def compute_deep(filters):
    summary = compute_summary(filters)
    buckets = summary["buckets"]

    result = {
        "filters": summary["filters"],
        "source": summary["source"],
        "has_data": summary["has_data"],
    }
    if not summary["has_data"]:
        return result

    totals = [bucket["total"] for bucket in buckets]
    total = summary["total_vehicles"]
    by_class = summary["by_class"]

    timeline, hourly_totals, hourly_classes = [], [0] * 24, [dict() for _ in range(24)]
    matrix = [[0] * 24 for _ in range(7)]
    daily = {}
    days_seen_by_hour = [set() for _ in range(24)]
    running = 0
    cumulative = []

    for index, bucket in enumerate(buckets):
        moment = _local(bucket["timestamp"])
        window = totals[max(0, index - 3): index + 1]
        running += bucket["total"]
        gap = index > 0 and (moment - _local(buckets[index - 1]["timestamp"])) > timedelta(minutes=45)
        timeline.append({
            "t": moment.isoformat(),
            "label": moment.strftime("%d/%m %H:%M"),
            "total": bucket["total"],
            "ma": round(sum(window) / len(window), 2),
            "by_class": bucket["by_class"],
            "gap_before": bool(gap),
        })
        cumulative.append({"t": moment.isoformat(), "value": running})

        hourly_totals[moment.hour] += bucket["total"]
        days_seen_by_hour[moment.hour].add(moment.date())
        for name, count in bucket["by_class"].items():
            hourly_classes[moment.hour][name] = hourly_classes[moment.hour].get(name, 0) + count
        matrix[moment.weekday()][moment.hour] += bucket["total"]

        day = daily.setdefault(moment.date().isoformat(), {"total": 0, "by_class": {}})
        day["total"] += bucket["total"]
        for name, count in bucket["by_class"].items():
            day["by_class"][name] = day["by_class"].get(name, 0) + count

    hourly = [
        {
            "hour": hour,
            "total": hourly_totals[hour],
            "avg_per_day": round(hourly_totals[hour] / len(days_seen_by_hour[hour]), 1) if days_seen_by_hour[hour] else 0,
            "by_class": hourly_classes[hour],
        }
        for hour in range(24)
    ]
    peak_hour = max(hourly, key=lambda item: item["total"])

    weekday_totals = [sum(row) for row in matrix]
    peak_weekday = max(range(7), key=lambda i: weekday_totals[i]) if any(weekday_totals) else None

    daily_list = []
    previous_total = None
    for day_key in sorted(daily):
        entry = {"date": day_key, "total": daily[day_key]["total"], "by_class": daily[day_key]["by_class"]}
        entry["delta_pct"] = _pct(entry["total"] - previous_total, previous_total) if previous_total else None
        previous_total = entry["total"]
        daily_list.append(entry)

    classes = [
        {"name": name, "total": count, "pct": _pct(count, total)}
        for name, count in sorted(by_class.items(), key=lambda kv: -kv[1])
    ]

    heat = get_heatmap_data(filters)
    camera_rows = (heat.get("cameras") or []) + (heat.get("unplaced") or [])
    cameras = [
        {
            "key": camera["camera_key"],
            "name": camera["name"],
            "total": camera["total"],
            "pct": _pct(camera["total"], total),
            "average": camera["average"],
            "peak": camera["peak"],
            "peak_timestamp": camera["peak_timestamp"],
            "by_class": camera["by_class"],
            "intensity": camera["intensity"],
        }
        for camera in sorted(camera_rows, key=lambda item: -item["total"])
        if camera["total"] > 0
    ]

    top_windows = sorted(timeline, key=lambda item: -item["total"])[:8]

    occurrences = get_occurrences(filters)
    occurrence_counts, occurrence_hours = {}, [0] * 24
    for event in occurrences.get("events", []):
        label = OCCURRENCE_LABELS.get(event.get("type"), str(event.get("type")))
        occurrence_counts[label] = occurrence_counts.get(label, 0) + 1
        try:
            occurrence_hours[_local(event["timestamp"]).hour] += 1
        except (KeyError, TypeError, ValueError):
            pass

    previous = _previous_period(filters)
    previous_days = len({_local(bucket["timestamp"]).date() for bucket in previous["buckets"]})
    # Só compara com o período anterior se ele tem leituras em tantos dias quanto
    # o atual: comparar um dia com leitura contra sete seria enganoso.
    comparable = previous["total_vehicles"] > 0 and previous_days == len(daily_list)
    delta_total = (total - previous["total_vehicles"]) if comparable else None

    heavy = sum(by_class.get(name, 0) for name in HEAVY_CLASSES)
    nonzero = [value for value in totals if value > 0]
    average = round(total / len(totals), 2)
    peak_value = max(totals)

    result.update({
        "kpis": {
            "total": total,
            "windows": len(totals),
            "average": average,
            "median": round(statistics.median(totals), 1),
            "std": round(statistics.pstdev(totals), 2) if len(totals) > 1 else 0,
            "peak": peak_value,
            "peak_at": summary["peak_bucket"]["timestamp"],
            "peak_ratio": round(peak_value / average, 2) if average else 0,
            "min_nonzero": min(nonzero) if nonzero else 0,
            "monitored_hours": round(len(totals) * 15 / 60, 1),
            "busiest_hour": peak_hour["hour"],
            "busiest_hour_total": peak_hour["total"],
            "busiest_weekday": WEEKDAYS[peak_weekday] if peak_weekday is not None else None,
            "per_hour_rate": round(total / max(1, len(totals) * 15 / 60), 1),
            "heavy_pct": _pct(heavy, total),
            "top_class": classes[0]["name"] if classes else None,
            "top_class_pct": classes[0]["pct"] if classes else 0,
            "days": len(daily_list),
            "period_days": _period_days(filters),
            "cameras": len(cameras),
            "occurrences": len(occurrences.get("events", [])),
            "previous_total": previous["total_vehicles"],
            "delta_total": delta_total,
            "delta_pct": _pct(delta_total, previous["total_vehicles"]) if comparable else None,
        },
        "timeline": timeline,
        "cumulative": cumulative,
        "hourly": hourly,
        "weekday_hour": {"labels": WEEKDAYS, "matrix": matrix, "weekday_totals": weekday_totals},
        "daily": daily_list,
        "classes": classes,
        "cameras": cameras,
        "top_windows": top_windows,
        "histogram": _histogram(totals),
        "occurrences": {"by_type": occurrence_counts, "by_hour": occurrence_hours},
    })
    return result
