"""Geografia do mapa: estados, municípios e contorno oficiais (IBGE) e busca de
endereços (OpenStreetMap/Nominatim).

Tudo passa pelo servidor, com cache em disco: o navegador nunca fala direto com
esses serviços (menos exposição de quem usa) e uma queda externa não derruba o
painel. Os parâmetros são validados antes de qualquer requisição externa e só
hosts fixos são acessados.
"""

import json
import re
import threading
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "geo_cache"

IBGE = "https://servicodados.ibge.gov.br/api"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
# A política de uso do Nominatim exige identificar a aplicação e no máximo 1 requisição/s.
USER_AGENT = "VIA-Mobilidade-Urbana/1.0 (plataforma de inteligencia para mobilidade urbana)"
STATIC_TTL = 30 * 24 * 3600  # estados, municípios e contornos mudam raramente
SEARCH_TTL = 24 * 3600
TIMEOUT = 10

BRAZIL_LAT = (-34.0, 6.0)
BRAZIL_LNG = (-74.5, -28.0)

_memory = {}
_lock = threading.Lock()
_search_lock = threading.Lock()
_last_search = [0.0]


class GeoUnavailable(Exception):
    """Serviço externo indisponível e sem cópia em cache."""


def _cache_path(key):
    return CACHE_DIR / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".json")


def _cache_get(key, ttl):
    now = time.time()
    with _lock:
        hit = _memory.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    path = _cache_path(key)
    try:
        if path.exists() and now - path.stat().st_mtime < ttl:
            value = json.loads(path.read_text(encoding="utf-8"))
            with _lock:
                _memory[key] = (now, value)
            return value
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _cache_stale(key):
    """Cópia antiga serve de reserva quando o serviço externo cai."""
    path = _cache_path(key)
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _cache_set(key, value):
    with _lock:
        _memory[key] = (time.time(), value)
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(key).write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _fetch(url, params=None, headers=None):
    response = requests.get(
        url, params=params, timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})},
    )
    response.raise_for_status()
    return response.json()


def _cached_fetch(key, ttl, url, params=None):
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached
    try:
        value = _fetch(url, params)
    except (requests.RequestException, ValueError):
        stale = _cache_stale(key)
        if stale is not None:
            return stale
        raise GeoUnavailable("Serviço de mapas indisponível no momento.")
    _cache_set(key, value)
    return value


# ---- estados e municípios (IBGE) -------------------------------------------------

def estados():
    data = _cached_fetch("estados", STATIC_TTL, f"{IBGE}/v1/localidades/estados", {"orderBy": "nome"})
    return [{"sigla": item["sigla"], "nome": item["nome"]} for item in data]


def valid_uf(uf):
    uf = (uf or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", uf):
        raise ValueError("Estado inválido.")
    if uf not in {item["sigla"] for item in estados()}:
        raise ValueError("Estado inválido.")
    return uf


def municipios(uf):
    uf = valid_uf(uf)
    data = _cached_fetch(f"municipios_{uf}", STATIC_TTL, f"{IBGE}/v1/localidades/estados/{uf}/municipios", {"orderBy": "nome"})
    return [{"id": item["id"], "nome": item["nome"]} for item in data]


def valid_ibge_id(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{7}", text):
        raise ValueError("Município inválido.")
    return int(text)


def _bbox(geometry):
    """(sul, oeste, norte, leste) de qualquer Polygon/MultiPolygon GeoJSON."""
    south = west = 10**9
    north = east = -10**9

    def walk(node):
        nonlocal south, west, north, east
        if node and isinstance(node[0], (int, float)):
            lng, lat = node[0], node[1]
            south, north = min(south, lat), max(north, lat)
            west, east = min(west, lng), max(east, lng)
        else:
            for child in node:
                walk(child)

    walk(geometry["coordinates"])
    return [south, west, north, east]


def municipio(ibge_id):
    """Dados do município com contorno: {id, nome, uf, center:[lat,lng], bbox, geometry}."""
    ibge_id = valid_ibge_id(ibge_id)
    cached = _cache_get(f"municipio_{ibge_id}", STATIC_TTL)
    if cached is not None:
        return cached

    info = _cached_fetch(f"municipio_info_{ibge_id}", STATIC_TTL, f"{IBGE}/v1/localidades/municipios/{ibge_id}")
    if not info:
        raise ValueError("Município não encontrado.")
    try:
        uf = info["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    except (KeyError, TypeError):
        uf = (info.get("regiao-imediata", {}).get("regiao-intermediaria", {}).get("UF", {}) or {}).get("sigla")

    shape = _cached_fetch(
        f"municipio_malha_{ibge_id}", STATIC_TTL,
        f"{IBGE}/v3/malhas/municipios/{ibge_id}",
        {"formato": "application/vnd.geo+json", "qualidade": "minima"},
    )
    features = shape.get("features") or []
    if not features:
        raise GeoUnavailable("Contorno do município indisponível.")
    geometry = features[0]["geometry"]
    south, west, north, east = _bbox(geometry)
    result = {
        "id": ibge_id,
        "nome": info["nome"],
        "uf": uf,
        "center": [round((south + north) / 2, 6), round((west + east) / 2, 6)],
        "bbox": [south, west, north, east],
        "geometry": geometry,
    }
    _cache_set(f"municipio_{ibge_id}", result)
    return result


def municipio_basic(ibge_id):
    """Só id, nome e UF (leve, usado ao salvar a escolha no login)."""
    ibge_id = valid_ibge_id(ibge_id)
    info = _cached_fetch(f"municipio_info_{ibge_id}", STATIC_TTL, f"{IBGE}/v1/localidades/municipios/{ibge_id}")
    if not info:
        raise ValueError("Município não encontrado.")
    try:
        uf = info["microrregiao"]["mesorregiao"]["UF"]["sigla"]
    except (KeyError, TypeError):
        uf = None
    return {"id": ibge_id, "nome": info["nome"], "uf": uf}


# ---- busca de endereços (Nominatim) ----------------------------------------------

def in_brazil(lat, lng):
    return BRAZIL_LAT[0] <= lat <= BRAZIL_LAT[1] and BRAZIL_LNG[0] <= lng <= BRAZIL_LNG[1]


def geocode(query, bbox=None, hint=None):
    """Até 5 resultados [{lat, lng, label}] para um endereço/lugar digitado.

    `bbox` (sul, oeste, norte, leste) restringe à região do município escolhido;
    `hint` ("Cidade, UF") é anexado quando a busca restrita não acha nada.
    """
    query = " ".join(str(query or "").split())[:200]
    if len(query) < 3:
        raise ValueError("Digite pelo menos 3 caracteres.")

    def run(q, bounded):
        key = "geo_" + re.sub(r"\W+", "_", f"{q}_{bbox if bounded else ''}").lower()[:150]
        cached = _cache_get(key, SEARCH_TTL)
        if cached is not None:
            return cached
        params = {"q": q, "format": "jsonv2", "limit": 5, "countrycodes": "br"}
        if bounded and bbox:
            south, west, north, east = bbox
            params.update({"viewbox": f"{west},{north},{east},{south}", "bounded": 1})
        with _search_lock:
            wait = 1.1 - (time.time() - _last_search[0])
            if wait > 0:
                time.sleep(wait)
            try:
                raw = _fetch(NOMINATIM, params)
            except (requests.RequestException, ValueError):
                raise GeoUnavailable("Busca de endereços indisponível no momento.")
            finally:
                _last_search[0] = time.time()
        found = []
        for item in raw:
            try:
                lat, lng = float(item["lat"]), float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if in_brazil(lat, lng):
                found.append({"lat": round(lat, 6), "lng": round(lng, 6), "label": str(item.get("display_name", ""))[:160]})
        _cache_set(key, found)
        return found

    results = run(query, True) if bbox else run(query, False)
    if not results and hint:
        results = run(f"{query}, {hint}", False)
    return results
