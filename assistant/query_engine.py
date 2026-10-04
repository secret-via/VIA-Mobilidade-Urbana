"""Motor determinístico de consultas sobre os dados reais do VIA.

Única fonte de verdade para números agregados (fluxo, picos, comparação de
períodos, ocorrências) — usada pela Análise Personalizada, pelo chatbot de IA
e pelo relatório em PDF, garantindo que os três sempre mostrem exatamente os
mesmos valores. Nunca inventa dados: quando não há histórico suficiente para
o período pedido, os campos ``has_data``/``source`` deixam isso explícito
para quem consome o resultado.

Prioriza o PostgreSQL (histórico completo, ``DATABASE_BACKEND=postgres``) e
cai para ``logs/events.jsonl`` (mesmo formato de evento, ver
``traffic/events.py``) quando o banco não está configurado.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

from dashboard.app import (
    REPORT_BUCKET_MINUTES,
    _new_bucket,
    aggregate_vehicle_events,
    summarize_buckets,
)
from config.config import BR_TIMEZONE
from data.postgres import create_database

ROOT_DIR = Path(__file__).resolve().parents[1]
OCCURRENCE_EVENT_TYPES = (
    "CONGESTION_STARTED",
    "CONGESTION_ENDED",
    "VEHICLE_STOPPED",
)


@dataclass
class QueryFilters:
    date_from: date
    date_to: date
    hour_from: Optional[time] = None
    hour_to: Optional[time] = None
    camera_key: Optional[str] = None
    vehicle_type: Optional[str] = None
    # Organização dona dos dados. Preenchido pelo servidor a partir da sessão
    # (nunca vem do cliente); None só no modo local sem contas.
    org_id: Optional[int] = None
    # Janela corrida (ex.: "últimas 24 h até agora"). Quando presentes, valem no
    # lugar de date_from/date_to, que ficam só como rótulo do período.
    since: Optional[datetime] = None
    until: Optional[datetime] = None


def _events_path():
    return ROOT_DIR / "logs" / "events.jsonl"


def _backend():
    return os.getenv("DATABASE_BACKEND", "").lower()


def _date_range(filters):
    """Converte o intervalo de datas (calendário de Brasília) em [since, until)
    tz-aware. As datas do filtro (ex.: "hoje") sempre significam o dia civil
    em horário de Brasília, então a hora é atribuída diretamente em
    BR_TIMEZONE em vez de converter a partir do fuso do sistema operacional.
    """
    if filters.since is not None:
        return filters.since, filters.until or datetime.now(timezone.utc)
    since = datetime.combine(filters.date_from, time.min, tzinfo=BR_TIMEZONE)
    until = datetime.combine(filters.date_to + timedelta(days=1), time.min, tzinfo=BR_TIMEZONE)
    return since, until


def _hour_range(filters):
    if filters.hour_from is None or filters.hour_to is None:
        return None
    return (filters.hour_from.hour, filters.hour_to.hour)


def _filters_to_dict(filters):
    payload = asdict(filters)
    payload.pop("org_id", None)
    payload.pop("since", None)
    payload.pop("until", None)
    payload["date_from"] = filters.date_from.isoformat()
    payload["date_to"] = filters.date_to.isoformat()
    payload["hour_from"] = filters.hour_from.isoformat() if filters.hour_from else None
    payload["hour_to"] = filters.hour_to.isoformat() if filters.hour_to else None
    return payload


def _bucketize_events(events, bucket_minutes, hour_range=None):
    """Agrupa uma lista de eventos (dicts já filtrados, ex. vindos do Postgres)
    em janelas fixas, na mesma forma que ``aggregate_vehicle_events`` produz
    a partir do JSONL (reaproveita ``_new_bucket``).
    """
    bucket_seconds = bucket_minutes * 60
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    buckets = {}

    for event in events:
        raw_timestamp = event.get("timestamp") or event.get("created_at")
        if not raw_timestamp:
            continue
        try:
            moment = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)

        if hour_range is not None:
            lo, hi = hour_range
            local_hour = moment.astimezone(BR_TIMEZONE).hour
            in_range = (lo <= local_hour < hi) if lo <= hi else (local_hour >= lo or local_hour < hi)
            if not in_range:
                continue

        offset = (moment - epoch).total_seconds() % bucket_seconds
        bucket_start = moment - timedelta(seconds=offset)
        key = bucket_start.isoformat()

        bucket = buckets.setdefault(key, _new_bucket(key))
        class_name = str(event.get("class_name") or "desconhecido")
        camera_id = str(event.get("camera_id") or "desconhecido")

        bucket["total"] += 1
        bucket["by_class"][class_name] = bucket["by_class"].get(class_name, 0) + 1
        per_camera = bucket["by_camera"].setdefault(camera_id, {})
        per_camera[class_name] = per_camera.get(class_name, 0) + 1

    return [buckets[key] for key in sorted(buckets.keys())]


def _iter_jsonl_events(path):
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _filter_jsonl_events(path, event_types, since, until=None, camera_key=None, org_id=None):
    results = []
    for event in _iter_jsonl_events(path):
        if event.get("type") not in event_types:
            continue
        if org_id is not None and event.get("org_id") != org_id:
            continue
        raw_timestamp = event.get("timestamp")
        if not raw_timestamp:
            continue
        try:
            moment = datetime.fromisoformat(raw_timestamp)
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        if moment < since:
            continue
        if until is not None and moment >= until:
            continue
        if camera_key is not None and str(event.get("camera_id")) != str(camera_key):
            continue
        results.append(event)
    return results


def data_source_status(org_id=None):
    """Indica de onde os dados viriam para uma consulta agora, sem exigir filtros."""
    if _backend() == "postgres":
        db = create_database()
        has_data = db.has_events_since(datetime(1970, 1, 1, tzinfo=timezone.utc), org_id=org_id)
        return {"backend": "postgres", "has_data": bool(has_data)}

    path = _events_path()
    has_data = path.exists() and path.stat().st_size > 0
    return {"backend": "jsonl" if has_data else "none", "has_data": has_data}


def window_summary(since, org_id=None, legacy_org_id=None):
    """Total e distribuição por classe de uma janela corrida (resumo mínimo da
    aba Estatísticas). Mesma fonte dos demais números: nada é estimado."""
    if _backend() == "postgres":
        events = create_database().query_events(["VEHICLE_DETECTED"], since, org_id=org_id)
        buckets = _bucketize_events(events, REPORT_BUCKET_MINUTES)
    else:
        buckets = aggregate_vehicle_events(
            _events_path(), since, org_id=org_id, legacy_org_id=legacy_org_id
        )
    summary = summarize_buckets(buckets)

    # O "gostinho" que a tela mostra de graça: só estes três números. O resto da análise
    # (séries, câmeras, comparações) só existe no PDF.
    peak = busiest = None
    if buckets:
        top = max(buckets, key=lambda bucket: bucket["total"])
        peak = {"total": top["total"], "at": top["timestamp"]}
        by_hour = {}
        for bucket in buckets:
            hour = datetime.fromisoformat(bucket["timestamp"]).astimezone(BR_TIMEZONE).hour
            by_hour[hour] = by_hour.get(hour, 0) + bucket["total"]
        best = max(by_hour, key=by_hour.get)
        busiest = {"hour": best, "total": by_hour[best]}

    return {
        "total_vehicles": summary["total_vehicles"],
        "by_class": summary["by_class"],
        "peak": peak,
        "busiest_hour": busiest,
    }


def get_buckets(filters, bucket_minutes=REPORT_BUCKET_MINUTES, event_types=("VEHICLE_DETECTED",)):
    """Retorna (buckets, source) — source é 'postgres', 'jsonl' ou 'none'."""
    since, until = _date_range(filters)
    hour_range = _hour_range(filters)

    if _backend() == "postgres":
        db = create_database()
        events = db.query_events(
            list(event_types), since, until=until,
            camera_key=filters.camera_key, class_name=filters.vehicle_type,
            org_id=filters.org_id,
        )
        return _bucketize_events(events, bucket_minutes, hour_range), "postgres"

    path = _events_path()
    buckets = aggregate_vehicle_events(
        path, since, bucket_minutes=bucket_minutes, until=until,
        camera_id=filters.camera_key, class_name=filters.vehicle_type,
        hour_range=hour_range, event_types=event_types, org_id=filters.org_id,
    )
    return buckets, ("jsonl" if path.exists() else "none")


def compute_summary(filters, event_types=("VEHICLE_DETECTED",)):
    """Contrato comum consumido pela Análise Personalizada, pelo chatbot e pelo PDF."""
    buckets, source = get_buckets(filters, event_types=event_types)
    summary = summarize_buckets(buckets)
    peak_bucket = max(buckets, key=lambda bucket: bucket["total"], default=None)
    total = summary["total_vehicles"]

    return {
        "filters": _filters_to_dict(filters),
        "source": source,
        "has_data": bool(buckets),
        "buckets": buckets,
        "total_vehicles": total,
        "by_class": summary["by_class"],
        "by_camera": summary["by_camera"],
        "peak_bucket": peak_bucket,
        "average_per_bucket": round(total / len(buckets), 2) if buckets else 0,
    }


def compare_periods(filters_a, filters_b):
    period_a = compute_summary(filters_a)
    period_b = compute_summary(filters_b)

    delta_total = period_b["total_vehicles"] - period_a["total_vehicles"]
    delta_pct = None
    if period_a["total_vehicles"]:
        delta_pct = round(delta_total / period_a["total_vehicles"] * 100, 1)

    classes = set(period_a["by_class"]) | set(period_b["by_class"])
    delta_by_class = {
        class_name: period_b["by_class"].get(class_name, 0) - period_a["by_class"].get(class_name, 0)
        for class_name in classes
    }

    return {
        "period_a": period_a,
        "period_b": period_b,
        "delta_total": delta_total,
        "delta_pct": delta_pct,
        "delta_by_class": delta_by_class,
        "has_data": period_a["has_data"] or period_b["has_data"],
    }


def get_heatmap_data(filters):
    """Intensidade de fluxo por câmera no período/filtros, para o mapa de
    calor. A escala vem do min/max real dos totais no recorte pedido — nunca
    de um valor fixo arbitrário.
    """
    buckets, source = get_buckets(filters)
    summary = summarize_buckets(buckets)

    per_camera_detail = {}
    for camera_key, classes in summary["by_camera"].items():
        peak = 0
        peak_timestamp = None
        buckets_with_camera = 0
        for bucket in buckets:
            camera_bucket = bucket["by_camera"].get(camera_key)
            if not camera_bucket:
                continue
            buckets_with_camera += 1
            total = sum(camera_bucket.values())
            if total > peak:
                peak = total
                peak_timestamp = bucket["timestamp"]

        total = sum(classes.values())
        per_camera_detail[camera_key] = {
            "total": total,
            "average": round(total / buckets_with_camera, 2) if buckets_with_camera else 0,
            "peak": peak,
            "peak_timestamp": peak_timestamp,
            "predominant_class": max(classes, key=classes.get) if classes else None,
            "by_class": classes,
        }

    registered = {}
    if _backend() == "postgres":
        registered = {
            camera["camera_key"]: camera
            for camera in create_database().list_cameras(org_id=filters.org_id)
        }

    values = [detail["total"] for detail in per_camera_detail.values()]
    value_min, value_max = (min(values), max(values)) if values else (0, 0)

    cameras_out = []
    unplaced = []
    for camera_key in set(per_camera_detail) | set(registered):
        detail = per_camera_detail.get(camera_key, {
            "total": 0, "average": 0, "peak": 0, "peak_timestamp": None,
            "predominant_class": None, "by_class": {},
        })
        registration = registered.get(camera_key)
        entry = {
            "camera_key": camera_key,
            "name": registration["name"] if registration else camera_key,
            "location_label": registration["location_label"] if registration else None,
            "map_x": registration["map_x"] if registration else None,
            "map_y": registration["map_y"] if registration else None,
            "total": detail["total"],
            "average": detail["average"],
            "peak": detail["peak"],
            "peak_timestamp": detail["peak_timestamp"],
            "predominant_class": detail["predominant_class"],
            "by_class": detail["by_class"],
            "intensity": (
                round((detail["total"] - value_min) / (value_max - value_min), 3)
                if value_max > value_min
                else (1.0 if detail["total"] > 0 else 0.0)
            ),
        }
        target = unplaced if entry["map_x"] is None or entry["map_y"] is None else cameras_out
        target.append(entry)

    cameras_out.sort(key=lambda item: item["total"], reverse=True)
    unplaced.sort(key=lambda item: item["total"], reverse=True)

    return {
        "filters": _filters_to_dict(filters),
        "source": source,
        "has_data": bool(values) and value_max > 0,
        "cameras": cameras_out,
        "unplaced": unplaced,
        "intensity_scale": {"min": value_min, "max": value_max},
    }


def get_occurrences(filters):
    since, until = _date_range(filters)
    events = []
    source = "none"

    if _backend() == "postgres":
        db = create_database()
        events = db.query_events(
            list(OCCURRENCE_EVENT_TYPES), since, until=until,
            camera_key=filters.camera_key, org_id=filters.org_id,
        )
        source = "postgres"

    if not events:
        jsonl_events = _filter_jsonl_events(
            _events_path(), OCCURRENCE_EVENT_TYPES, since, until, filters.camera_key, org_id=filters.org_id
        )
        if jsonl_events:
            events = jsonl_events
            source = "jsonl"

    return {
        "filters": _filters_to_dict(filters),
        "source": source,
        "has_data": bool(events),
        "events": events,
    }
