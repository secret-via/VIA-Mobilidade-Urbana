import ipaddress
import json
import socket
import tempfile
import threading
import time
from collections import Counter, deque
from datetime import date, datetime, time as time_of_day, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from config.config import BR_TIMEZONE

LOCAL_CAMERA_ID = "cam_local"
REPORT_RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
REPORT_BUCKET_MINUTES = 15


def event_in_org(event, org_id, legacy_org_id=None):
    """True se o evento pertence à organização `org_id`.

    `org_id=None` (modo local sem contas) não filtra nada. Eventos gravados
    antes do multi-cliente não têm `org_id`: pertencem à organização interna.
    """
    if org_id is None:
        return True
    owner = event.get("org_id")
    if owner is None:
        owner = legacy_org_id
    return owner == org_id


def validate_public_stream_url(raw):
    """Valida a URL de câmera informada por um cliente (não-admin).

    Clientes só podem cadastrar streams de rede públicos: nada de índice de
    dispositivo, caminho de arquivo do servidor, nem endereços internos
    (localhost, redes privadas, metadados de nuvem), que permitiriam usar o
    servidor para alcançar a rede da VIA. Devolve a URL limpa ou levanta
    ValueError com mensagem em português.
    """
    text = str(raw or "").strip()
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("rtsp", "rtsps", "http", "https") or not parts.hostname:
        raise ValueError("Informe a URL do stream da câmera (rtsp://, http:// ou https://).")

    host = parts.hostname
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parts.port or 80, proto=socket.IPPROTO_TCP)
        except OSError:
            raise ValueError("Não foi possível resolver o endereço da câmera.")
        addresses = {ipaddress.ip_address(info[4][0]) for info in infos}

    for address in addresses:
        if not address.is_global:
            raise ValueError("Endereço de câmera não permitido (rede interna ou reservada).")
    return text


class LoginThrottle:
    """Limita tentativas de login erradas por (IP, e-mail): 8 a cada 15 min."""

    def __init__(self, max_attempts=8, window_seconds=900):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.failures = {}
        self.lock = threading.Lock()

    def _recent(self, key):
        cutoff = time.monotonic() - self.window
        attempts = self.failures.setdefault(key, deque())
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts

    def blocked(self, key):
        with self.lock:
            return len(self._recent(key)) >= self.max_attempts

    def fail(self, key):
        with self.lock:
            self._recent(key).append(time.monotonic())

    def reset(self, key):
        with self.lock:
            self.failures.pop(key, None)


def to_traffic_update(snapshot, camera_id):
    """Traduz o snapshot interno para o contrato esperado pelo front (VIA | WD).

    O front (dashboard/templates/index.html) só entende mensagens no formato
    {"type": "traffic_update", "cameraId": ..., "data": {...}}; veja
    TrafficIntelligence.ingest() no script embutido na página.
    """
    congestion = snapshot.get("congestion") or {}
    return {
        "type": "traffic_update",
        "cameraId": camera_id,
        "data": {
            "vehicles": snapshot.get("objects", 0),
            "visible": snapshot.get("visible", {}),
            "visible_recent": snapshot.get("visible_recent", {}),
            "rolling_window_seconds": snapshot.get("rolling_window_seconds", 12),
            "stopped": snapshot.get("stopped", 0),
            "entry": snapshot.get("entries", 0),
            "exit": snapshot.get("exits", 0),
            "flow_per_minute": snapshot.get("flow_per_minute", 0),
            "congestion": {"level": congestion.get("level")},
        },
    }


def resolve_camera_source(raw, root):
    """Aceita índice de dispositivo (0, 1, 2...) ou caminho/URL de câmera virtual.

    Devolve (source, is_device, loop_when_finished).
    """
    text = str(raw).strip()
    try:
        return int(text), True, False
    except ValueError:
        pass

    if text.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
        return text, False, False

    candidate = Path(text)
    if not candidate.is_absolute():
        candidate = root / text
    if candidate.exists():
        return str(candidate), False, True

    raise ValueError(
        f"Fonte de câmera inválida: '{raw}'. Use um índice (0, 1, 2...), "
        "o caminho de um arquivo de vídeo existente, ou uma URL rtsp:// / http(s)://."
    )


class DashboardService:
    """Uma câmera (física, arquivo de vídeo ou stream de rede) + um YOLO
    e tracker dedicados a ela.

    Cada câmera tem seu próprio processo de rastreamento (ByteTrack guarda
    estado no objeto do modelo), então compartilhar um único modelo entre
    câmeras misturaria os IDs rastreados. Por isso cada câmera nova carrega
    seu próprio modelo, ao custo de mais RAM por câmera.
    """

    def __init__(self, model_path, camera_source=0, camera_id=None, is_device=True,
                 loop_when_finished=False, org_id=None):
        import cv2
        from ultralytics import YOLO
        from utils.pipeline import TrafficProcessor

        self.cv2 = cv2
        self.loop_when_finished = loop_when_finished

        if is_device:
            self.capture = cv2.VideoCapture(camera_source, cv2.CAP_DSHOW)
        else:
            self.capture = cv2.VideoCapture(camera_source)

        if not self.capture.isOpened():
            raise RuntimeError(
                f"Não foi possível abrir a câmera '{camera_source}'. "
                "Verifique se ela está conectada, se o caminho/URL está certo, "
                "e se não está em uso por outro programa."
            )

        if is_device:
            from config.config import CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS

            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
            self.capture.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

        self.camera_source = camera_source
        self.camera_id = camera_id
        self.org_id = org_id
        self.model_path = str(model_path)

        self.processor = TrafficProcessor(YOLO(str(model_path)), camera_id=camera_id, org_id=org_id)

        self.lock = threading.Lock()
        self.last_frame = None
        self.last_jpeg = None
        self.closed = False

        self.worker = threading.Thread(target=self._camera_loop, daemon=True)
        self.worker.start()

    def _camera_loop(self):
        while not self.closed:
            ok, frame = self.capture.read()

            if not ok:
                if self.loop_when_finished:
                    self.capture.set(self.cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                print(f"⚠️ Não foi possível capturar um frame da câmera {self.camera_source}.")
                time.sleep(0.1)
                continue

            # Descarta frames que já chegaram enquanto o anterior era
            # processado, para nunca acumular atraso: sempre trabalha em cima
            # do frame mais recente disponível. Em hardware rápido isso não
            # descarta nada (o buffer fica vazio); em hardware mais fraco, o
            # FPS efetivo cai sozinho em vez de a transmissão atrasar.
            for _ in range(5):
                if not self.capture.grab():
                    break
                ok2, newer = self.capture.retrieve()
                if not ok2:
                    break
                frame = newer

            try:
                processed = self.processor.process(frame)

                ok, encoded = self.cv2.imencode(".jpg", processed, [self.cv2.IMWRITE_JPEG_QUALITY, 80])
                if not ok:
                    print(f"⚠️ Não foi possível codificar o frame da câmera {self.camera_source}.")
                    continue

                with self.lock:
                    self.last_frame = processed
                    self.last_jpeg = encoded.tobytes()

            except Exception:
                import traceback

                print(f"❌ Erro no processamento da IA (câmera {self.camera_source}):")
                traceback.print_exc()
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            return self.last_jpeg

    def snapshot(self):
        with self.lock:
            snapshot = dict(self.processor.last_snapshot)

        try:
            snapshot["database"] = self.processor.database.summary()
        except Exception as error:
            snapshot["database"] = {"status": "indisponível", "detail": str(error)}

        snapshot["camera"] = {
            "connected": bool(self.capture.isOpened() and not self.closed),
            "source": str(self.camera_source),
            "width": int(self.capture.get(self.cv2.CAP_PROP_FRAME_WIDTH) or 0),
            "height": int(self.capture.get(self.cv2.CAP_PROP_FRAME_HEIGHT) or 0),
            "fps": float(self.capture.get(self.cv2.CAP_PROP_FPS) or 0),
            "pipeline": "active" if self.last_jpeg is not None else "starting",
        }
        snapshot["model"] = {
            "version": snapshot.get("model_version"),
            "path": self.model_path,
            "status": "loaded",
        }

        return snapshot

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.capture.release()
        except Exception:
            pass


class BrowserPushService:
    """Uma câmera cuja fonte é o navegador de quem acessa o site, não o
    servidor: em vez de um `_camera_loop` lendo de `cv2.VideoCapture`, os
    frames chegam de fora via `push_frame()` (um por mensagem WebSocket
    binária, ver rota `/ws/webcam/<camera_id>`) e são processados ali mesmo,
    de forma síncrona, na thread daquela conexão.

    Implementa a mesma interface pública que `DashboardService`
    (`get_frame`, `snapshot`, `close`) para que `/video/<id>`, `/api/cameras`
    e `/ws/status` continuem funcionando sem distinguir a origem da câmera.
    """

    def __init__(self, model_path, camera_id=None, org_id=None):
        import cv2
        from ultralytics import YOLO
        from utils.pipeline import TrafficProcessor

        self.cv2 = cv2
        self.camera_id = camera_id
        self.org_id = org_id
        self.model_path = str(model_path)
        self.processor = TrafficProcessor(YOLO(str(model_path)), camera_id=camera_id, org_id=org_id)

        self.lock = threading.Lock()
        self.last_frame = None
        self.last_jpeg = None
        self.last_push_at = None
        self.frame_size = (0, 0)
        self.closed = False

    def push_frame(self, jpeg_bytes):
        """Decodifica um JPEG recebido do navegador e roda a IA nele."""
        import numpy as np

        if self.closed:
            return

        array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = self.cv2.imdecode(array, self.cv2.IMREAD_COLOR)
        if frame is None:
            return

        processed = self.processor.process(frame)
        ok, encoded = self.cv2.imencode(".jpg", processed, [self.cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return

        with self.lock:
            self.last_frame = processed
            self.last_jpeg = encoded.tobytes()
            self.last_push_at = time.monotonic()
            self.frame_size = (int(processed.shape[1]), int(processed.shape[0]))

    def get_frame(self):
        with self.lock:
            return self.last_jpeg

    def snapshot(self):
        with self.lock:
            snapshot = dict(self.processor.last_snapshot)
            last_push_at = self.last_push_at
            width, height = self.frame_size
            has_jpeg = self.last_jpeg is not None

        try:
            snapshot["database"] = self.processor.database.summary()
        except Exception as error:
            snapshot["database"] = {"status": "indisponível", "detail": str(error)}

        # Sem captura própria para consultar: "conectada" aqui significa que
        # algum frame chegou do navegador nos últimos segundos.
        connected = last_push_at is not None and (time.monotonic() - last_push_at) < 5

        snapshot["camera"] = {
            "connected": bool(connected and not self.closed),
            "source": "browser",
            "width": width,
            "height": height,
            "fps": 0,
            "pipeline": "active" if has_jpeg else "starting",
        }
        snapshot["model"] = {
            "version": snapshot.get("model_version"),
            "path": self.model_path,
            "status": "loaded",
        }

        return snapshot

    def close(self):
        self.closed = True


class CameraManager:
    """Registro de todas as câmeras que o backend está processando com IA.

    Adicionar uma câmera aqui (via `/api/cameras` ou `/api/cameras/browser`)
    é o que garante que ela tenha detecção de verdade: qualquer câmera
    conectada só pelo front (HLS, WHEP, RTSP direto no browser, ou a opção
    "webcam sem IA") mostra vídeo mas nunca aparece aqui, então nunca recebe
    eventos de `traffic_update` — é vídeo puro, sem IA, por design.
    """

    def __init__(self, model_path):
        self.model_path = model_path
        self.services = {}
        self.lock = threading.Lock()
        self._next_index = 1

    def _allocate_id(self, camera_id):
        with self.lock:
            if camera_id is None:
                while f"cam_{self._next_index}" in self.services:
                    self._next_index += 1
                camera_id = f"cam_{self._next_index}"
            elif camera_id in self.services:
                raise ValueError(f"Já existe uma câmera com o id {camera_id}.")
            return camera_id

    def add(self, source, camera_id=None, is_device=True, loop_when_finished=False, org_id=None):
        camera_id = self._allocate_id(camera_id)

        service = DashboardService(
            self.model_path,
            source,
            camera_id=camera_id,
            is_device=is_device,
            loop_when_finished=loop_when_finished,
            org_id=org_id,
        )

        with self.lock:
            self.services[camera_id] = service

        return camera_id

    def add_browser(self, camera_id=None, org_id=None):
        camera_id = self._allocate_id(camera_id)

        service = BrowserPushService(self.model_path, camera_id=camera_id, org_id=org_id)

        with self.lock:
            self.services[camera_id] = service

        return camera_id

    def count_browser(self):
        with self.lock:
            return sum(1 for service in self.services.values() if isinstance(service, BrowserPushService))

    def remove(self, camera_id):
        with self.lock:
            service = self.services.pop(camera_id, None)
        if service:
            service.close()

    def get(self, camera_id, org_id=None):
        """Câmera pelo id. Com `org_id`, só devolve se pertencer à organização
        (câmera de outro cliente se comporta como inexistente)."""
        service = self.services.get(camera_id)
        if service is not None and org_id is not None and service.org_id != org_id:
            return None
        return service

    def items(self, org_id=None):
        with self.lock:
            items = list(self.services.items())
        if org_id is None:
            return items
        return [(camera_id, service) for camera_id, service in items if service.org_id == org_id]


def _new_bucket(key):
    return {"timestamp": key, "total": 0, "by_class": {}, "by_camera": {}}


def aggregate_vehicle_events(path, since, bucket_minutes=REPORT_BUCKET_MINUTES,
                              until=None, camera_id=None, class_name=None,
                              hour_range=None, event_types=("VEHICLE_DETECTED",),
                              org_id=None, legacy_org_id=None):
    """Agrupa eventos (por padrão VEHICLE_DETECTED, já deduplicados por
    track_id na origem) em janelas fixas, para os relatórios de 24h/7
    dias/30 dias e para a Análise Personalizada (assistant/query_engine.py).

    Parâmetros extras (todos opcionais, sem afetar o comportamento existente
    de /api/reports quando omitidos):
    - until: exclui eventos a partir deste instante (tz-aware).
    - camera_id: filtra por identificador de câmera (string, ex. "cam_1").
    - class_name: filtra por classe detectada (ex. "carro").
    - hour_range: tupla (hora_inicial, hora_final) em horário local (0-23);
      se hora_inicial > hora_final, o intervalo cruza a meia-noite.
    - event_types: tipos de evento aceitos (por padrão só contagem de
      veículos).
    - org_id / legacy_org_id: restringe à organização (ver event_in_org).
    """
    if not path.exists():
        return []

    bucket_seconds = bucket_minutes * 60
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    buckets = {}

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") not in event_types:
                continue
            if not event_in_org(event, org_id, legacy_org_id):
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
            if camera_id is not None and str(event.get("camera_id")) != str(camera_id):
                continue
            if class_name is not None and event.get("class_name") != class_name:
                continue
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
            event_class_name = str(event.get("class_name") or "desconhecido")
            event_camera_id = str(event.get("camera_id") or "desconhecido")

            bucket["total"] += 1
            bucket["by_class"][event_class_name] = bucket["by_class"].get(event_class_name, 0) + 1
            per_camera = bucket["by_camera"].setdefault(event_camera_id, {})
            per_camera[event_class_name] = per_camera.get(event_class_name, 0) + 1

    return [buckets[key] for key in sorted(buckets.keys())]


def summarize_buckets(buckets):
    by_class = Counter()
    by_camera = {}
    for bucket in buckets:
        for class_name, count in bucket["by_class"].items():
            by_class[class_name] += count
        for camera_id, classes in bucket["by_camera"].items():
            camera_totals = by_camera.setdefault(camera_id, Counter())
            for class_name, count in classes.items():
                camera_totals[class_name] += count

    return {
        "total_vehicles": sum(by_class.values()),
        "by_class": dict(by_class),
        "by_camera": {camera_id: dict(counts) for camera_id, counts in by_camera.items()},
    }


def create_app(model_path, camera_id=0):
    import hashlib
    import os
    import secrets
    from functools import wraps

    from flask import Flask, Response, g, jsonify, redirect, render_template, request, send_file, session, url_for

    from flask_sock import Sock
    from config.config import LEARNING_ENABLED, MAX_BROWSER_CAMERAS
    from config.plans import (
        PLANS,
        ROLE_MEMBER,
        ROLE_OWNER,
        ROLE_VIA_ADMIN,
        get_plan,
        plan_allows,
        within_limit,
    )
    from data.postgres import create_database
    from geo import service as geo

    # Import tardio: assistant.query_engine importa funções deste próprio
    # módulo (dashboard.app) para reaproveitar a agregação de eventos, então
    # só pode ser importado depois que este módulo termina de carregar.
    from assistant.query_engine import (
        QueryFilters,
        data_source_status,
        window_summary,
    )
    from assistant.chat_service import answer_question, is_data_question
    from assistant.providers.factory import get_provider
    from reports.pdf_builder import build_report_pdf

    root = Path(__file__).resolve().parents[1]

    app = Flask(__name__, template_folder=str(root / "dashboard" / "templates"))
    app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # Em produção (HTTPS) defina VIA_HTTPS=1 para o cookie nunca trafegar em HTTP.
        SESSION_COOKIE_SECURE=os.environ.get("VIA_HTTPS", "").strip().lower() in ("1", "true", "yes"),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,  # maior upload aceito: a foto de perfil
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    if not os.environ.get("FLASK_SECRET_KEY"):
        print("AVISO: FLASK_SECRET_KEY não definida: os logins são invalidados a cada reinício do servidor.")

    # Modo multi-cliente: com PostgreSQL, o acesso é por conta (e-mail + senha),
    # cada usuário pertence a uma organização com plano e só enxerga os dados
    # dela. Sem PostgreSQL (uso local/demonstração) vale o modo antigo: uma
    # senha global opcional (VIA_ACCESS_PASSWORD) e nenhum limite de plano.
    store = None
    internal_org_id = None
    if os.environ.get("DATABASE_BACKEND", "").strip().lower() == "postgres":
        # Falha fechada de propósito: com PostgreSQL configurado, o servidor
        # não sobe aberto se as contas não puderem ser carregadas.
        from accounts.store import AccountStore
        from data.postgres import PostgresDatabase

        accounts_db = PostgresDatabase()
        accounts_db.initialize()  # migrações idempotentes (colunas org_id etc.)
        store = AccountStore(accounts_db)
        store.initialize()
        internal_org_id = store.ensure_internal_org()
        if not store.has_any_user():
            print("AVISO: Nenhum usuário cadastrado. Crie o primeiro admin: "
                  "python scripts/gerenciar_contas.py criar-admin --email ... --senha ...")

    access_password = os.environ.get("VIA_ACCESS_PASSWORD")
    if store is None and not access_password:
        print("AVISO: VIA_ACCESS_PASSWORD não definida: o dashboard está acessível sem senha.")

    manager = CameraManager(model_path)
    database = create_database()
    try:
        manager.add(camera_id, camera_id=LOCAL_CAMERA_ID, is_device=True, loop_when_finished=False, org_id=internal_org_id)
        database.upsert_camera(LOCAL_CAMERA_ID, "Câmera local", org_id=internal_org_id)
    except RuntimeError as exc:
        # Sem webcam neste PC o painel sobe do mesmo jeito; as câmeras são cadastradas pela aba Câmeras.
        print(f"AVISO: câmera local indisponível ({exc}). O painel segue sem ela.")

    sock = Sock(app)
    throttle = LoginThrottle()

    # Modo antigo: a sessão guarda um marcador derivado da senha atual; trocar
    # a senha no .env invalida quem já estava logado.
    session_token = hashlib.sha256(f"{app.secret_key}:{access_password}".encode()).hexdigest()[:24]

    # ---- autenticação --------------------------------------------------

    def _wants_json():
        return request.path.startswith(("/api/", "/ws/", "/video"))

    def _same_origin():
        """Defesa em profundidade contra CSRF além do SameSite=Lax: requisições
        que alteram estado só valem se vierem do próprio site."""
        site = request.headers.get("Sec-Fetch-Site")
        if site is not None:
            return site in ("same-origin", "none")
        origin = request.headers.get("Origin")
        if origin:
            return urlsplit(origin).netloc == request.host
        return True

    @app.before_request
    def require_login():
        g.user = None
        g.org_id = None

        if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _same_origin():
            return jsonify({"error": "Origem não permitida."}), 403

        if request.path.startswith("/static/"):
            return None

        if store is None:
            if request.path == "/login" or not access_password or session.get("authenticated") == session_token:
                return None
        else:
            user_id = session.get("user_id")
            user = store.get_user(user_id) if user_id else None
            if user and user["active"] and session.get("sv") == user["session_version"] and (
                user["role"] == ROLE_VIA_ADMIN or user["org"]["status"] == "active"
            ):
                g.user = user
                g.org_id = user["org_id"]
                return None
            if user_id:
                session.clear()  # conta desativada, suspensa ou plano vencido
            if request.path == "/login":
                return None

        if _wants_json():
            return jsonify({"error": "Não autenticado."}), 401
        return redirect(url_for("login", next=request.path))

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith(("/api/", "/configuracoes", "/login")) and request.path != "/api/me/avatar":
            response.headers["Cache-Control"] = "no-store"
        return response

    def role_required(*roles):
        def decorator(view):
            @wraps(view)
            def wrapped(*args, **kwargs):
                # Modo local sem contas: sem papéis, tudo liberado como antes.
                if store is not None and (g.user is None or g.user["role"] not in roles):
                    return jsonify({"error": "Sem permissão para esta ação."}), 403
                return view(*args, **kwargs)

            return wrapped

        return decorator

    def current_plan():
        return get_plan(g.user["org"]["plan"]) if g.user else None

    def feature_blocked(feature):
        """Resposta de erro se o plano da organização não inclui o recurso."""
        if g.user is not None and not plan_allows(g.user["org"]["plan"], feature):
            label = current_plan()["label"]
            return jsonify({
                "error": f"Este recurso não está incluído no plano {label}.",
                "plan_limit": True,
            }), 403
        return None

    def _safe_next(target):
        # Só caminhos internos: evita redirecionar o usuário para outro site.
        if target and target.startswith("/") and not target.startswith("//"):
            return target
        return None

    @app.get("/login")
    def login():
        authenticated = g.user is not None if store is not None else (
            not access_password or session.get("authenticated") == session_token
        )
        if authenticated:
            return redirect(url_for("index"))
        return render_template("login.html", error=None, multi_tenant=store is not None)

    @app.post("/login")
    def login_submit():
        password = request.form.get("password", "")

        if store is None:
            if access_password and secrets.compare_digest(password, access_password):
                session.permanent = True
                session["authenticated"] = session_token
                return redirect(_safe_next(request.args.get("next")) or url_for("index"))
            return render_template("login.html", error="Senha incorreta.", multi_tenant=False), 401

        email = request.form.get("email", "")
        key = (request.remote_addr, email.strip().lower())
        if throttle.blocked(key):
            return render_template(
                "login.html", error="Muitas tentativas. Aguarde alguns minutos.", multi_tenant=True
            ), 429

        user, error = store.authenticate(email, password)
        if user is None:
            throttle.fail(key)
            return render_template("login.html", error=error, multi_tenant=True), 401

        throttle.reset(key)
        session.clear()
        session.permanent = True
        session["user_id"] = user["id"]
        session["sv"] = user["session_version"]
        target = _safe_next(request.args.get("next")) or url_for("index")
        if not user["municipio"]:
            # Primeiro acesso: estado e município são escolhidos uma única vez.
            return redirect(url_for("first_access", next=target))
        return redirect(target)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/primeiro-acesso")
    def first_access():
        """Escolha única de estado e município (o mapa abre nele). Quem já escolheu pula."""
        target = _safe_next(request.args.get("next")) or url_for("index")
        if g.user is None or g.user["municipio"]:
            return redirect(target)
        return render_template("first_access.html", next_url=target, name=g.user["name"] or g.user["email"])

    def _account_summary(user):
        if user is None:
            return None
        words = (user["name"] or user["email"].split("@")[0]).replace(".", " ").replace("_", " ").split()
        return {
            "name": user["name"] or user["email"],
            "initials": "".join(word[0] for word in words[:2]).upper() or "?",
            "plan_label": get_plan(user["org"]["plan"])["label"],
            "org_name": user["org"]["name"],
            "avatar_url": f"/api/me/avatar?v={user['avatar_version']}" if user["avatar_version"] else None,
        }

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            auth_enabled=bool(store is not None or access_password),
            user=g.user,
            account=_account_summary(g.user),
        )

    # ---- conta, organização e administração ------------------------------

    def _limits_payload(org):
        plan = get_plan(org["plan"])
        return {
            "plan": org["plan"],
            "plan_label": plan["label"],
            "status": org["status"],
            "plan_expires_at": org["plan_expires_at"],
            "max_users": plan["max_users"],
            "max_cameras": plan["max_cameras"],
            "pdf_per_month": plan["pdf_per_month"],
            "chat_per_month": plan["chat_per_month"],
            "features": sorted(plan["features"]),
        }

    def _org_overview(org_id):
        org = store.get_org(org_id)
        from accounts.store import org_status

        org["status"] = org_status(org)
        return {
            "org": {"name": org["name"], **_limits_payload(org)},
            "usage": {
                "chat": store.usage(org_id, "chat"),
                "pdf": store.usage(org_id, "pdf"),
                "cameras": len(manager.items(org_id)),
                "users": store.count_active_users(org_id),
            },
        }

    @app.get("/api/me")
    def me():
        if g.user is None:
            # Modo local sem contas.
            return jsonify({"multi_tenant": False, "has_local_camera": True})
        payload = _org_overview(g.org_id)
        return jsonify({
            "multi_tenant": True,
            "email": g.user["email"],
            "name": g.user["name"],
            "role": g.user["role"],
            "municipio": g.user["municipio"],
            "avatar_url": f"/api/me/avatar?v={g.user['avatar_version']}" if g.user["avatar_version"] else None,
            "has_local_camera": manager.get(LOCAL_CAMERA_ID, g.org_id) is not None,
            **payload,
        })

    @app.patch("/api/me")
    def update_me():
        if g.user is None:
            return jsonify({"error": "Disponível apenas com contas."}), 400
        payload = request.get_json(silent=True) or {}
        try:
            user = store.update_name(g.user["id"], payload.get("name"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"name": user["name"]})

    @app.post("/api/me/password")
    def change_my_password():
        if g.user is None:
            return jsonify({"error": "Disponível apenas com contas."}), 400
        payload = request.get_json(silent=True) or {}
        key = ("pw", request.remote_addr, g.user["id"])
        if throttle.blocked(key):
            return jsonify({"error": "Muitas tentativas. Aguarde alguns minutos."}), 429
        try:
            version = store.change_password(g.user["id"], payload.get("current"), payload.get("new"))
        except ValueError as error:
            throttle.fail(key)
            return jsonify({"error": str(error)}), 400
        throttle.reset(key)
        session["sv"] = version  # esta sessão continua; as outras caem
        return jsonify({"status": "ok"})

    AVATAR_DIR = Path(os.environ.get("VIA_AVATAR_DIR") or root / "data" / "avatars")

    def _avatar_path(user_id):
        return AVATAR_DIR / f"{int(user_id)}.jpg"

    @app.get("/api/me/avatar")
    def my_avatar():
        """Foto do próprio usuário (cada usuário só alcança a sua)."""
        if g.user is None or not g.user["avatar_version"] or not _avatar_path(g.user["id"]).exists():
            return "", 404
        # Lê o arquivo (poucos KB) em vez de entregá-lo aberto: no Windows um arquivo em
        # streaming fica "em uso" e não poderia ser trocado ou removido logo em seguida.
        response = Response(_avatar_path(g.user["id"]).read_bytes(), mimetype="image/jpeg")
        response.headers["Cache-Control"] = "private, max-age=86400"  # a versão na URL renova o cache
        return response

    @app.post("/api/me/avatar")
    def upload_avatar():
        if g.user is None:
            return jsonify({"error": "Disponível apenas com contas."}), 400
        upload = request.files.get("file")
        if upload is None:
            return jsonify({"error": "Escolha uma imagem."}), 400
        data = upload.read(3 * 1024 * 1024 + 1)
        if len(data) > 3 * 1024 * 1024:
            return jsonify({"error": "A imagem pode ter no máximo 3 MB."}), 413
        try:
            import io as _io

            from PIL import Image, ImageOps

            image = Image.open(_io.BytesIO(data))
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("formato")
            if image.width * image.height > 25_000_000:
                raise ValueError("tamanho")
            # Reprocessa do zero (recorte quadrado, 256 px, JPEG): descarta metadados
            # (localização, câmera) e qualquer conteúdo embutido no arquivo original.
            image = ImageOps.fit(ImageOps.exif_transpose(image).convert("RGB"), (256, 256), Image.LANCZOS)
        except Exception:
            return jsonify({"error": "Imagem inválida. Use JPG, PNG ou WebP de até 3 MB."}), 400
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        image.save(_avatar_path(g.user["id"]), "JPEG", quality=88, optimize=True)
        version = store.bump_avatar(g.user["id"])
        return jsonify({"avatar_url": f"/api/me/avatar?v={version}"})

    @app.delete("/api/me/avatar")
    def delete_avatar():
        if g.user is None:
            return jsonify({"error": "Disponível apenas com contas."}), 400
        try:
            _avatar_path(g.user["id"]).unlink()
        except (FileNotFoundError, PermissionError):
            pass  # sem arquivo, ou ainda em uso: com a versão zerada ele deixa de ser servido
        store.clear_avatar(g.user["id"])
        return jsonify({"status": "removed"})

    @app.get("/api/settings/cameras")
    def settings_cameras():
        """Câmeras da organização para a página Configurações > Câmeras:
        só nome, tipo e se está conectada (nunca a URL de origem)."""
        names = {camera["camera_key"]: camera["name"] for camera in database.list_cameras(org_id=g.org_id)}
        cameras = []
        for cam_id, service in manager.items(g.org_id):
            if isinstance(service, BrowserPushService):
                kind = "Webcam do navegador"
            elif isinstance(getattr(service, "camera_source", None), int):
                kind = "Câmera do servidor"
            else:
                kind = "Stream de rede"
            cameras.append({
                "name": names.get(cam_id) or cam_id,
                "kind": kind,
                "connected": bool(service.snapshot()["camera"]["connected"]),
            })
        cameras.sort(key=lambda camera: camera["name"].lower())
        return jsonify(cameras)

    # ---- conversas do assistente VIA (privadas por usuário) ----------------

    def _chat_user_only():
        if store is None or g.user is None:
            return jsonify({"error": "O histórico de conversas requer contas."}), 501
        return None

    @app.get("/api/chat/conversations")
    def chat_conversations():
        unavailable = _chat_user_only()
        return unavailable or jsonify(store.chat_list(g.user["id"]))

    @app.post("/api/chat/conversations")
    def chat_new():
        unavailable = _chat_user_only()
        if unavailable:
            return unavailable
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(store.chat_create(g.org_id, g.user["id"], payload.get("title"))), 201
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    @app.get("/api/chat/conversations/<int:conv_id>")
    def chat_open(conv_id):
        unavailable = _chat_user_only()
        if unavailable:
            return unavailable
        conversation = store.chat_get(g.user["id"], conv_id)
        if conversation is None:
            return jsonify({"error": "Conversa não encontrada."}), 404
        return jsonify({
            "id": conversation["id"],
            "title": conversation["title"],
            "messages": store.chat_messages(g.user["id"], conv_id),
        })

    @app.patch("/api/chat/conversations/<int:conv_id>")
    def chat_rename(conv_id):
        unavailable = _chat_user_only()
        if unavailable:
            return unavailable
        payload = request.get_json(silent=True) or {}
        try:
            ok = store.chat_rename(g.user["id"], conv_id, payload.get("title"))
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"status": "ok"}) if ok else (jsonify({"error": "Conversa não encontrada."}), 404)

    @app.delete("/api/chat/conversations/<int:conv_id>")
    def chat_remove(conv_id):
        unavailable = _chat_user_only()
        if unavailable:
            return unavailable
        if not store.chat_delete(g.user["id"], conv_id):
            return jsonify({"error": "Conversa não encontrada."}), 404
        return jsonify({"status": "removed"})

    @app.post("/api/chat/conversations/<int:conv_id>/messages")
    def chat_send(conv_id):
        unavailable = _chat_user_only()
        if unavailable:
            return unavailable
        payload = request.get_json(silent=True) or {}
        content = str(payload.get("content") or "").strip()
        if not content:
            return jsonify({"error": "Escreva uma pergunta."}), 400
        if len(content) > 2000:
            return jsonify({"error": "A pergunta pode ter no máximo 2000 caracteres."}), 400
        conversation = store.chat_get(g.user["id"], conv_id)
        if conversation is None:
            return jsonify({"error": "Conversa não encontrada."}), 404
        if conversation["messages"] >= store.MAX_MESSAGES:
            return jsonify({"error": "Esta conversa ficou muito longa. Comece uma nova."}), 400

        blocked = _chat_gate() if is_data_question(content) else None
        if blocked:
            return jsonify({"limit_reached": True, "answer": blocked})

        previous = store.chat_last_intent(g.user["id"], conv_id)
        result = answer_question(content, org_id=g.org_id, previous_intent=previous)
        has_data = bool(result["data"].get("has_data"))
        store.chat_add(g.user["id"], conv_id, "user", content)
        store.chat_add(g.user["id"], conv_id, "assistant", result["answer"], {"intent": result["intent"], "has_data": has_data})

        title = conversation["title"]
        if title == "Nova conversa":
            title = " ".join(content.split())[:60]
            store.chat_rename(g.user["id"], conv_id, title)
        return jsonify({"answer": result["answer"], "intent": result["intent"] if has_data else None, "title": title})

    # ---- páginas de Configurações (área da conta) ------------------------------

    SETTINGS_PAGES = [
        ("perfil", "Perfil", None),
        ("seguranca", "Segurança", None),
        ("plano", "Plano e uso", None),
        ("equipe", "Equipe", (ROLE_OWNER, ROLE_VIA_ADMIN)),
        ("cameras", "Câmeras", None),
        ("ajuda", "Ajuda e privacidade", None),
        ("administracao", "Administração VIA", (ROLE_VIA_ADMIN,)),
    ]

    @app.get("/conta")
    def account_page():
        return redirect(url_for("settings_page", page="plano"))

    @app.get("/configuracoes")
    def settings_home():
        return redirect(url_for("settings_page", page="perfil"))

    @app.get("/configuracoes/<page>")
    def settings_page(page):
        if g.user is None:
            return redirect(url_for("index"))
        visible = [
            (key, label) for key, label, roles in SETTINGS_PAGES
            if roles is None or g.user["role"] in roles
        ]
        if page not in dict(visible):
            return redirect(url_for("settings_page", page="perfil"))
        plan_labels = {key: plan["label"] for key, plan in PLANS.items()}
        return render_template(
            "settings.html",
            user=g.user,
            account=_account_summary(g.user),
            page=page,
            nav=visible,
            plan_labels=plan_labels,
        )

    def _public_user(user):
        return {key: user[key] for key in ("id", "email", "name", "role", "active", "last_login_at")}

    @app.get("/api/org/users")
    @role_required(ROLE_OWNER, ROLE_VIA_ADMIN)
    def org_users():
        return jsonify([_public_user(user) for user in store.list_users(g.org_id)])

    @app.post("/api/org/users")
    @role_required(ROLE_OWNER, ROLE_VIA_ADMIN)
    def org_create_user():
        payload = request.get_json(silent=True) or {}
        # O responsável da organização cria apenas usuários comuns; papéis
        # privilegiados são atribuídos pela equipe VIA.
        role = ROLE_MEMBER
        if g.user["role"] == ROLE_VIA_ADMIN and payload.get("role") in (ROLE_MEMBER, ROLE_OWNER):
            role = payload["role"]
        try:
            user = store.create_user(
                g.org_id, payload.get("email"), payload.get("password"), role=role, name=payload.get("name")
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify(_public_user(user)), 201

    @app.post("/api/org/users/<int:user_id>/active")
    @role_required(ROLE_OWNER, ROLE_VIA_ADMIN)
    def org_set_user_active(user_id):
        payload = request.get_json(silent=True) or {}
        active = bool(payload.get("active"))
        if user_id == g.user["id"] and not active:
            return jsonify({"error": "Você não pode desativar o próprio usuário."}), 400
        if active:
            # Reativar também ocupa uma vaga do plano.
            plan = get_plan(g.user["org"]["plan"])
            if not within_limit(plan["max_users"], store.count_active_users(g.org_id)):
                return jsonify({"error": "Limite de usuários do plano atingido."}), 400
        user = store.set_user_active(g.org_id, user_id, active)
        if user is None:
            return jsonify({"error": "Usuário não encontrado."}), 404
        return jsonify(_public_user(user))

    @app.get("/admin")
    def admin_page():
        return redirect(url_for("settings_page", page="administracao"))

    @app.get("/api/admin/orgs")
    @role_required(ROLE_VIA_ADMIN)
    def admin_list_orgs():
        orgs = store.list_orgs()
        for org in orgs:
            org["cameras"] = len(manager.items(org["id"]))
            org["limits"] = _limits_payload({**org})
            org.pop("created_at", None)
        return jsonify(orgs)

    @app.post("/api/admin/orgs")
    @role_required(ROLE_VIA_ADMIN)
    def admin_create_org():
        """Cria a organização e o primeiro usuário (responsável) de uma vez."""
        payload = request.get_json(silent=True) or {}
        try:
            expires = _parse_expiry(payload.get("plan_expires_at"))
            org = store.create_org(payload.get("name"), payload.get("plan") or "intelligence", expires)
            owner = store.create_user(
                org["id"], payload.get("owner_email"), payload.get("owner_password"),
                role=ROLE_OWNER, name=payload.get("owner_name"),
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        return jsonify({"org": {"name": org["name"], "plan": org["plan"]}, "owner": {"email": owner["email"]}}), 201

    @app.patch("/api/admin/orgs/<int:org_id>")
    @role_required(ROLE_VIA_ADMIN)
    def admin_update_org(org_id):
        payload = request.get_json(silent=True) or {}
        if org_id == internal_org_id and ("active" in payload or "plan" in payload):
            return jsonify({"error": "A organização interna não pode ser suspensa nem trocar de plano."}), 400
        kwargs = {}
        try:
            if "plan" in payload:
                kwargs["plan"] = payload["plan"]
            if "active" in payload:
                kwargs["active"] = bool(payload["active"])
            if "plan_expires_at" in payload:
                kwargs["plan_expires_at"] = _parse_expiry(payload["plan_expires_at"])
            org = store.update_org(org_id, **kwargs)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        if org is None:
            return jsonify({"error": "Organização não encontrada."}), 404
        return jsonify({"plan": org["plan"], "active": org["active"]})

    def _parse_expiry(raw):
        if not raw:
            return None
        try:
            moment = datetime.fromisoformat(str(raw))
        except ValueError:
            raise ValueError("Vencimento inválido. Use AAAA-MM-DD.")
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=BR_TIMEZONE)
        return moment

    # ---- vídeo e dados ---------------------------------------------------

    def stream(service):
        def frames():
            while service and not service.closed:
                frame = service.get_frame()
                if frame is None:
                    time.sleep(0.05)
                    continue
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
                time.sleep(0.02)

        return Response(frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

    @app.get("/video")
    def video_default():
        service = manager.get(LOCAL_CAMERA_ID, g.org_id)
        if service is None:
            return jsonify({"error": "Câmera não encontrada."}), 404
        return stream(service)

    @app.get("/video/<camera_id>")
    def video_by_id(camera_id):
        service = manager.get(camera_id, g.org_id)
        if service is None:
            return jsonify({"error": "Câmera não encontrada."}), 404
        return stream(service)

    # Diagnóstico interno (caminho do modelo, banco, origem das câmeras): o painel
    # não usa, então só a equipe VIA enxerga.
    @app.get("/api/status")
    @role_required(ROLE_VIA_ADMIN)
    def status():
        service = manager.get(LOCAL_CAMERA_ID, g.org_id)
        if service is None and g.org_id is not None:
            owned = manager.items(g.org_id)
            service = owned[0][1] if owned else None
        return jsonify(service.snapshot() if service else {})

    def read_jsonl(path, limit=50, org_id=None):
        """Lê o histórico local sem expor arquivos arbitrários ao navegador."""
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_in_org(record, org_id, internal_org_id):
                records.append(record)
        return list(reversed(records[-limit:]))

    @app.get("/api/events")
    @role_required(ROLE_VIA_ADMIN)
    def events():
        return jsonify(read_jsonl(root / "logs" / "events.jsonl", org_id=g.org_id))

    # Aprendizado e modelos são da plataforma (pesos compartilhados), não de um
    # cliente: restritos à equipe VIA quando há contas.
    @app.get("/api/learning")
    @role_required(ROLE_VIA_ADMIN)
    def learning():
        queue = root / "data" / "learning_queue"
        counts = {
            name: len(list((queue / name).glob("*.json")))
            for name in ("pending", "approved", "rejected", "uncertain")
        }
        datasets = sorted(item.name for item in (root / "data").glob("dataset_v*"))
        return jsonify({"enabled": LEARNING_ENABLED, "cases": counts, "datasets": datasets})

    @app.get("/api/models")
    @role_required(ROLE_VIA_ADMIN)
    def models():
        def weights(folder):
            return [item.name for item in sorted(folder.glob("*.pt"))]

        production = root / "models" / "production"
        candidates = root / "models" / "candidates"
        return jsonify({
            "production": weights(production),
            "candidates": weights(candidates),
            "history": read_jsonl(root / "models" / "history.jsonl"),
        })

    @app.get("/api/reports")
    def reports():
        """Resumo mínimo (total e tipos) da janela corrida escolhida, para a aba
        Estatísticas. Detalhe por horário, câmera etc. só no PDF exportado."""
        range_key = request.args.get("range", "24h")
        if range_key not in REPORT_RANGES:
            range_key = "24h"
        since = datetime.now(timezone.utc) - REPORT_RANGES[range_key]
        summary = window_summary(since, org_id=g.org_id, legacy_org_id=internal_org_id)
        return jsonify({"range": range_key, **summary})

    def _parse_filters(payload):
        """Converte o corpo de /api/analytics/* em QueryFilters. Levanta
        ValueError com mensagem em português para o chamador responder 400.
        A organização vem sempre da sessão, nunca do corpo da requisição.
        """
        try:
            date_from = date.fromisoformat(payload["date_from"])
            date_to = date.fromisoformat(payload["date_to"])
        except (KeyError, ValueError):
            raise ValueError("Informe date_from e date_to no formato AAAA-MM-DD.")

        if date_to < date_from:
            raise ValueError("date_to não pode ser anterior a date_from.")

        hour_from = payload.get("hour_from")
        hour_to = payload.get("hour_to")
        try:
            hour_from = time_of_day.fromisoformat(hour_from) if hour_from else None
            hour_to = time_of_day.fromisoformat(hour_to) if hour_to else None
        except ValueError:
            raise ValueError("hour_from/hour_to devem estar no formato HH:MM.")

        return QueryFilters(
            date_from=date_from,
            date_to=date_to,
            hour_from=hour_from,
            hour_to=hour_to,
            camera_key=payload.get("camera_key") or None,
            vehicle_type=payload.get("vehicle_type") or None,
            org_id=g.org_id,
        )

    @app.post("/api/analytics/clear")
    @role_required(ROLE_VIA_ADMIN)
    def analytics_clear():
        """Zera as estatísticas acumuladas (Postgres + histórico local em
        JSONL). Não afeta câmeras cadastradas, modelos nem datasets. Com
        contas, só a equipe VIA pode e apenas os dados da própria organização
        (a interna); no modo local zera tudo, como antes.
        """
        database.clear_statistics(org_id=g.org_id)

        events_path = root / "logs" / "events.jsonl"
        if events_path.exists():
            if g.org_id is None:
                events_path.write_text("", encoding="utf-8")
            else:
                kept = []
                for line in events_path.read_text(encoding="utf-8").splitlines():
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not event_in_org(record, g.org_id, internal_org_id):
                        kept.append(line)
                events_path.write_text("".join(f"{line}\n" for line in kept), encoding="utf-8")

        return jsonify({"status": "cleared"})

    @app.get("/api/assistant/status")
    def assistant_status():
        provider = get_provider()
        payload = {"available": provider.available()}
        if g.user is None or g.user["role"] == ROLE_VIA_ADMIN:
            payload["provider"] = provider.name
            payload["data_source"] = data_source_status(g.org_id)
        return jsonify(payload)

    def _limit_reply(message):
        # 200 de propósito: o chat do front mostra `answer` como mensagem normal.
        return jsonify({"answer": message, "data": {"has_data": False}, "limit_reached": True})

    def _chat_gate():
        """None se a pergunta pode ser feita; senão a mensagem de bloqueio (plano ou
        limite mensal). Consome 1 unidade do limite quando libera."""
        if g.user is None:
            return None
        plan = current_plan()
        if not plan_allows(g.user["org"]["plan"], "assistant"):
            return f"O assistente VIA não está incluído no plano {plan['label']}."
        if not store.consume(g.org_id, "chat", plan["chat_per_month"]):
            return (
                "Você atingiu o limite mensal de consultas ao assistente do seu plano "
                f"({plan['label']}). Fale com a VIA para ampliar."
            )
        return None

    @app.post("/api/assistant/query")
    def assistant_query():
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Informe uma pergunta."}), 400

        blocked = _chat_gate() if is_data_question(question) else None
        if blocked:
            return _limit_reply(blocked)
        result = answer_question(question, org_id=g.org_id, previous_intent=payload.get("previous_intent"))
        return jsonify({
            "answer": result["answer"],
            "intent": result["intent"],
            "data": {"has_data": bool(result["data"].get("has_data"))},
        })

    @app.get("/api/reports/pdf")
    def report_pdf():
        blocked = feature_blocked("pdf")
        if blocked:
            return blocked
        try:
            filters = _parse_filters(request.args)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        if g.user is not None:
            plan = current_plan()
            if not store.consume(g.org_id, "pdf", plan["pdf_per_month"]):
                return jsonify({
                    "error": f"Limite mensal de relatórios do plano {plan['label']} atingido.",
                    "plan_limit": True,
                }), 429

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            out_path = Path(handle.name)

        build_report_pdf(filters, out_path)

        download_name = f"via-relatorio-{filters.date_from}-{filters.date_to}.pdf"
        return send_file(out_path, mimetype="application/pdf", as_attachment=True, download_name=download_name)

    # ---- câmeras -----------------------------------------------------------

    @app.get("/api/cameras/positions")
    def camera_positions():
        keys = ("camera_key", "name", "location_label", "lat", "lng", "active")
        return jsonify([{key: camera[key] for key in keys} for camera in database.list_cameras(org_id=g.org_id)])

    @app.post("/api/cameras/<camera_key>/location")
    def set_camera_location(camera_key):
        """Posição real da câmera (digitada, buscada por endereço ou arrastada no mapa)."""
        payload = request.get_json(silent=True) or {}
        try:
            lat = float(payload["lat"])
            lng = float(payload["lng"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "Informe lat e lng."}), 400
        if not geo.in_brazil(lat, lng):
            return jsonify({"error": "Coordenadas fora do Brasil."}), 400
        if g.org_id is not None and manager.get(camera_key, g.org_id) is None:
            return jsonify({"error": "Câmera não encontrada."}), 404
        label = str(payload.get("label") or "").strip()[:160] or None
        result = database.set_camera_location(camera_key, round(lat, 6), round(lng, 6), label, org_id=g.org_id)
        if result is None:
            return jsonify({"error": "Salvar a posição requer PostgreSQL ativo (DATABASE_BACKEND=postgres)."}), 409
        return jsonify({"lat": result["lat"], "lng": result["lng"], "location_label": result["location_label"]})

    # ---- mapa: estados, municípios e busca de endereço -----------------------------

    geo_throttle = LoginThrottle(max_attempts=40, window_seconds=60)

    def _geo_error(error):
        if isinstance(error, geo.GeoUnavailable):
            return jsonify({"error": str(error)}), 503
        return jsonify({"error": str(error)}), 400

    @app.get("/api/geo/estados")
    def geo_estados():
        try:
            return jsonify(geo.estados())
        except (ValueError, geo.GeoUnavailable) as error:
            return _geo_error(error)

    @app.get("/api/geo/municipios")
    def geo_municipios():
        try:
            return jsonify(geo.municipios(request.args.get("uf")))
        except (ValueError, geo.GeoUnavailable) as error:
            return _geo_error(error)

    @app.get("/api/geo/municipio/<int:ibge_id>")
    def geo_municipio(ibge_id):
        """Contorno e enquadramento do município para o mapa."""
        try:
            return jsonify(geo.municipio(ibge_id))
        except (ValueError, geo.GeoUnavailable) as error:
            return _geo_error(error)

    @app.get("/api/geo/buscar")
    def geo_buscar():
        key = ("geo", g.user["id"] if g.user else request.remote_addr)
        if geo_throttle.blocked(key):
            return jsonify({"error": "Muitas buscas seguidas. Aguarde um instante."}), 429
        geo_throttle.fail(key)  # conta cada busca na janela de 1 min
        bbox = hint = None
        muni = request.args.get("municipio")
        if muni:
            try:
                info = geo.municipio(muni)
                bbox, hint = info["bbox"], f"{info['nome']}, {info['uf']}"
            except (ValueError, geo.GeoUnavailable):
                pass
        try:
            return jsonify(geo.geocode(request.args.get("q"), bbox=bbox, hint=hint))
        except (ValueError, geo.GeoUnavailable) as error:
            return _geo_error(error)

    @app.post("/api/me/municipio")
    def set_my_municipio():
        if g.user is None:
            return jsonify({"error": "Disponível apenas com contas."}), 400
        payload = request.get_json(silent=True) or {}
        try:
            basic = geo.municipio_basic(payload.get("id"))
        except (ValueError, geo.GeoUnavailable) as error:
            return _geo_error(error)
        store.set_municipio(g.user["id"], basic["id"], basic["nome"], basic["uf"])
        return jsonify(basic)

    def _camera_quota_error():
        """Mensagem se a organização já usa todas as câmeras do plano."""
        if g.user is None:
            return None
        plan = current_plan()
        if not within_limit(plan["max_cameras"], len(manager.items(g.org_id))):
            return jsonify({
                "error": f"Limite de câmeras do plano {plan['label']} atingido ({plan['max_cameras']}).",
                "plan_limit": True,
            }), 403
        return None

    @app.get("/api/cameras")
    def list_cameras():
        # O painel só usa id e nome (filtro de relatório): a origem da câmera
        # (que pode ter usuário e senha na URL) nunca sai do servidor.
        names = {camera["camera_key"]: camera["name"] for camera in database.list_cameras(org_id=g.org_id)}
        return jsonify([
            {"id": cam_id, "name": names.get(cam_id) or cam_id}
            for cam_id, _service in manager.items(g.org_id)
        ])

    @app.post("/api/cameras")
    def add_camera():
        quota = _camera_quota_error()
        if quota:
            return quota

        payload = request.get_json(silent=True) or {}
        raw_source = payload.get("source", 0)
        name = payload.get("name")

        try:
            if g.user is not None and g.user["role"] != ROLE_VIA_ADMIN:
                # Clientes só cadastram streams de rede públicos; dispositivos e
                # arquivos do servidor são da operação VIA.
                source, is_device, loop_when_finished = validate_public_stream_url(raw_source), False, False
            else:
                source, is_device, loop_when_finished = resolve_camera_source(raw_source, root)
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

        try:
            camera_id = manager.add(
                source, is_device=is_device, loop_when_finished=loop_when_finished, org_id=g.org_id
            )
        except RuntimeError as error:
            # A mensagem interna cita a origem da câmera (pode conter credenciais).
            if g.user is not None and g.user["role"] != ROLE_VIA_ADMIN:
                return jsonify({"error": "Não foi possível conectar a esta câmera. Confira a URL e tente de novo."}), 409
            return jsonify({"error": str(error)}), 409

        database.upsert_camera(camera_id, name or camera_id, source=str(raw_source), org_id=g.org_id)

        return jsonify({"id": camera_id, "video_url": f"/video/{camera_id}"}), 201

    @app.post("/api/cameras/browser")
    def add_browser_camera():
        """Registra uma câmera cuja fonte é a webcam de quem acessa o site.

        Diferente de /api/cameras, não abre nada no servidor: só reserva o
        camera_id e cria o processador de IA. Os frames chegam depois via
        WebSocket em /ws/webcam/<camera_id>, enviados pelo navegador.
        """
        quota = _camera_quota_error()
        if quota:
            return quota

        if manager.count_browser() >= MAX_BROWSER_CAMERAS:
            return jsonify({
                "error": f"Limite de {MAX_BROWSER_CAMERAS} câmeras de navegador simultâneas atingido.",
            }), 429

        payload = request.get_json(silent=True) or {}
        name = payload.get("name")

        camera_id = manager.add_browser(org_id=g.org_id)
        database.upsert_camera(camera_id, name or camera_id, source="browser", org_id=g.org_id)

        return jsonify({"id": camera_id, "video_url": f"/video/{camera_id}"}), 201

    @app.delete("/api/cameras/<camera_id>")
    def remove_camera(camera_id):
        # Clientes nunca enxergam a câmera do servidor (get com org_id devolve None);
        # a equipe VIA pode excluí-la. Ela volta quando o servidor é reiniciado.
        if manager.get(camera_id, g.org_id) is None:
            return jsonify({"error": "Câmera não encontrada."}), 404
        manager.remove(camera_id)
        database.deactivate_camera(camera_id)
        return jsonify({"status": "removed"})

    @sock.route("/ws/status")
    def websocket_status(ws):
        org_id = g.org_id
        while True:
            try:
                for cam_id, service in manager.items(org_id):
                    if service.closed:
                        continue
                    data = to_traffic_update(service.snapshot(), cam_id)
                    ws.send(json.dumps(data, ensure_ascii=False, default=str))
                time.sleep(1)
            except Exception:
                break

    @sock.route("/ws/webcam/<camera_id>")
    def websocket_webcam(ws, camera_id):
        """Recebe frames JPEG (mensagens binárias) enviados pela webcam do
        navegador e roda o pipeline de IA em cada um, síncrono nesta mesma
        conexão. Uma mensagem de texto é tratada como erro do cliente e
        ignorada (o protocolo é só binário).
        """
        service = manager.get(camera_id, g.org_id)
        if service is None or not isinstance(service, BrowserPushService):
            ws.close(reason="Câmera de navegador não encontrada.")
            return

        while not service.closed:
            try:
                message = ws.receive(timeout=30)
            except Exception:
                break
            if message is None:
                break
            if isinstance(message, (bytes, bytearray)) and message:
                try:
                    service.push_frame(bytes(message))
                except Exception:
                    import traceback

                    print(f"❌ Erro no processamento da IA (câmera do navegador {camera_id}):")
                    traceback.print_exc()

    return app, manager
