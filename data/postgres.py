"""Camada PostgreSQL do sistema de trânsito."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _camera_row_to_dict(row):
    if row is None:
        return None
    (
        camera_pk,
        name,
        camera_key,
        location_label,
        map_x,
        map_y,
        active,
        created_at,
        updated_at,
        lat,
        lng,
    ) = row
    return {
        "id": camera_pk,
        "name": name,
        "camera_key": camera_key,
        "location_label": location_label,
        "map_x": map_x,
        "map_y": map_y,
        "active": active,
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "lat": lat,
        "lng": lng,
    }


class NullDatabase:
    """Banco vazio usado quando o PostgreSQL não está configurado."""

    def record_event(self, event):
        return None

    def record_detection(self, detection, frame_shape=None, org_id=None):
        return None

    def record_track(self, detection, org_id=None):
        return None

    def summary(self):
        return {
            "status": "offline",
            "backend": "none",
        }

    def upsert_camera(self, camera_key, name, source=None, org_id=None):
        return None

    def deactivate_camera(self, camera_key):
        return None

    def list_cameras(self, include_inactive=False, org_id=None):
        return []

    def set_camera_position(self, camera_key, map_x, map_y, location_label=None):
        return None

    def set_camera_location(self, camera_key, lat, lng, location_label=None, org_id=None):
        return None

    def query_events(self, event_types, since, until=None, camera_key=None, class_name=None, limit=None, org_id=None):
        return []

    def has_events_since(self, since, org_id=None):
        return False

    def clear_statistics(self, org_id=None):
        return None


class PostgresDatabase:
    """Persistência oficial do sistema no PostgreSQL."""

    def __init__(self):
        import psycopg

        self.psycopg = psycopg

        self.host = os.getenv("DATABASE_HOST", "localhost")
        self.port = int(os.getenv("DATABASE_PORT", "5432"))
        self.database = os.getenv("DATABASE_NAME", "transito_ia")
        self.user = os.getenv("DATABASE_USER", "postgres")
        self.password = os.getenv("DATABASE_PASSWORD", "")

        # Conexão reaproveitada entre chamadas. Antes, cada record_detection/
        # record_track abria e fechava uma conexão TCP nova a cada objeto
        # detectado em cada frame - com vários veículos em quadro isso são
        # dezenas de handshakes por segundo, e era a causa real da câmera
        # "travando" no dashboard (nada a ver com a internet do usuário: é
        # tudo local, entre o processo Python e o Postgres na mesma máquina).
        self._conn = None

    def connect(self):
        """Abre uma conexão nova e independente (uso pontual/CLI)."""
        return self.psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
        )

    def _get_connection(self):
        if self._conn is None or self._conn.closed:
            self._conn = self.psycopg.connect(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.user,
                password=self.password,
                autocommit=True,
            )
        return self._conn

    def _run(self, fn):
        """Executa fn(conn) na conexão persistente. Se a conexão caiu (rede,
        restart do Postgres), descarta e força reconexão na próxima chamada
        em vez de deixar todas as chamadas seguintes falharem também."""
        conn = self._get_connection()
        try:
            return fn(conn)
        except Exception:
            self._conn = None
            raise

    def test_connection(self):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_database(), version();")
                return cursor.fetchone()

        return self._run(_do)

    def initialize(self):
        schema = """
        CREATE TABLE IF NOT EXISTS cameras (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            camera_id INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS classes (
            id SERIAL PRIMARY KEY,
            class_id INTEGER UNIQUE NOT NULL,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS detections (
            id BIGSERIAL PRIMARY KEY,
            frame_id INTEGER,
            track_id INTEGER,
            class_id INTEGER,
            class_name TEXT,
            confidence DOUBLE PRECISION,
            bbox JSONB,
            center JSONB,
            status TEXT,
            model_version TEXT,
            frame_width INTEGER,
            frame_height INTEGER,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id BIGSERIAL PRIMARY KEY,
            track_id INTEGER NOT NULL,
            class_id INTEGER,
            class_name TEXT,
            confidence DOUBLE PRECISION,
            status TEXT,
            model_version TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS events (
            id BIGSERIAL PRIMARY KEY,
            event_type TEXT NOT NULL,
            event_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS memory (
            id BIGSERIAL PRIMARY KEY,
            memory_type TEXT,
            memory_data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS samples (
            id BIGSERIAL PRIMARY KEY,
            image_path TEXT,
            label_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS annotations (
            id BIGSERIAL PRIMARY KEY,
            sample_id BIGINT REFERENCES samples(id) ON DELETE CASCADE,
            class_id INTEGER,
            x_center DOUBLE PRECISION,
            y_center DOUBLE PRECISION,
            width DOUBLE PRECISION,
            height DOUBLE PRECISION
        );

        CREATE TABLE IF NOT EXISTS datasets (
            id BIGSERIAL PRIMARY KEY,
            version TEXT UNIQUE NOT NULL,
            path TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS models (
            id BIGSERIAL PRIMARY KEY,
            version TEXT UNIQUE NOT NULL,
            path TEXT,
            status TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS metrics (
            id BIGSERIAL PRIMARY KEY,
            model_version TEXT,
            precision DOUBLE PRECISION,
            recall DOUBLE PRECISION,
            map50 DOUBLE PRECISION,
            map50_95 DOUBLE PRECISION,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS external_context (
            id BIGSERIAL PRIMARY KEY,
            source TEXT,
            data JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS camera_key TEXT UNIQUE;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS location_label TEXT;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS map_x DOUBLE PRECISION;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS map_y DOUBLE PRECISION;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();

        ALTER TABLE events ADD COLUMN IF NOT EXISTS org_id INTEGER;
        ALTER TABLE detections ADD COLUMN IF NOT EXISTS org_id INTEGER;
        ALTER TABLE tracks ADD COLUMN IF NOT EXISTS org_id INTEGER;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS org_id INTEGER;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
        ALTER TABLE cameras ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;

        CREATE INDEX IF NOT EXISTS idx_events_org_type_created_at ON events (org_id, event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_cameras_org_id ON cameras (org_id);
        CREATE INDEX IF NOT EXISTS idx_events_event_type_created_at ON events (event_type, created_at);
        CREATE INDEX IF NOT EXISTS idx_events_camera_id ON events ((event_data->>'camera_id'));
        CREATE INDEX IF NOT EXISTS idx_events_class_name ON events ((event_data->>'class_name'));
        CREATE INDEX IF NOT EXISTS idx_events_created_at ON events (created_at);
        """

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(schema)

        self._run(_do)

    def seed_classes(self):
        classes = [
            (0, "carro"),
            (1, "moto"),
            (2, "onibus"),
            (3, "caminhao"),
            (4, "pessoa"),
            (5, "placa"),
        ]

        def _do(conn):
            with conn.cursor() as cursor:
                for class_id, name in classes:
                    cursor.execute(
                        """
                        INSERT INTO classes (class_id, name)
                        VALUES (%s, %s)
                        ON CONFLICT (class_id)
                        DO UPDATE SET name = EXCLUDED.name;
                        """,
                        (class_id, name),
                    )

        self._run(_do)

    def record_event(self, event):
        event_type = event.get("type", "UNKNOWN")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO events (event_type, event_data, org_id)
                    VALUES (%s, %s, %s);
                    """,
                    (event_type, self.psycopg.types.json.Jsonb(event), event.get("org_id")),
                )

        self._run(_do)

    def record_detection(self, detection, frame_shape=None, org_id=None):
        height = None
        width = None

        if frame_shape is not None:
            height, width = frame_shape[:2]

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO detections (
                        frame_id,
                        track_id,
                        class_id,
                        class_name,
                        confidence,
                        bbox,
                        center,
                        status,
                        model_version,
                        frame_width,
                        frame_height,
                        org_id
                    )
                    VALUES (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    );
                    """,
                    (
                        detection.get("frame_id"),
                        detection.get("track_id"),
                        detection.get("class_id"),
                        detection.get("class_name"),
                        detection.get("confidence"),
                        self.psycopg.types.json.Jsonb(
                            detection.get("bbox")
                        ),
                        self.psycopg.types.json.Jsonb(
                            detection.get("center")
                        ),
                        detection.get("status"),
                        detection.get("model_version"),
                        width,
                        height,
                        org_id,
                    ),
                )

        self._run(_do)

    def record_track(self, detection, org_id=None):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tracks (
                        track_id,
                        class_id,
                        class_name,
                        confidence,
                        status,
                        model_version,
                        org_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        detection.get("track_id"),
                        detection.get("class_id"),
                        detection.get("class_name"),
                        detection.get("confidence"),
                        detection.get("status"),
                        detection.get("model_version"),
                        org_id,
                    ),
                )

        self._run(_do)

    def summary(self):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM detections;")
                detections = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM tracks;")
                tracks = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM events;")
                events = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM samples;")
                samples = cursor.fetchone()[0]
            return detections, tracks, events, samples

        detections, tracks, events, samples = self._run(_do)

        return {
            "status": "online",
            "backend": "postgres",
            "database": self.database,
            "detections": detections,
            "tracks": tracks,
            "events": events,
            "samples": samples,
        }

    def upsert_camera(self, camera_key, name, source=None, org_id=None):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO cameras (name, camera_key, active, updated_at, org_id)
                    VALUES (%s, %s, TRUE, NOW(), %s)
                    ON CONFLICT (camera_key)
                    DO UPDATE SET name = EXCLUDED.name, active = TRUE, updated_at = NOW()
                    RETURNING id, name, camera_key, location_label, map_x, map_y, active, created_at, updated_at, lat, lng;
                    """,
                    (name, camera_key, org_id),
                )
                return cursor.fetchone()

        return _camera_row_to_dict(self._run(_do))

    def deactivate_camera(self, camera_key):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE cameras SET active = FALSE, updated_at = NOW()
                    WHERE camera_key = %s;
                    """,
                    (camera_key,),
                )

        self._run(_do)

    def list_cameras(self, include_inactive=False, org_id=None):
        query = """
            SELECT id, name, camera_key, location_label, map_x, map_y, active, created_at, updated_at, lat, lng
            FROM cameras
        """
        clauses, params = [], []
        if not include_inactive:
            clauses.append("active = TRUE")
        if org_id is not None:
            clauses.append("org_id = %s")
            params.append(org_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY name;"

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()

        return [_camera_row_to_dict(row) for row in self._run(_do)]

    def set_camera_position(self, camera_key, map_x, map_y, location_label=None):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO cameras (name, camera_key, map_x, map_y, location_label, active, updated_at)
                    VALUES (%s, %s, %s, %s, %s, TRUE, NOW())
                    ON CONFLICT (camera_key)
                    DO UPDATE SET
                        map_x = EXCLUDED.map_x,
                        map_y = EXCLUDED.map_y,
                        location_label = COALESCE(EXCLUDED.location_label, cameras.location_label),
                        updated_at = NOW()
                    RETURNING id, name, camera_key, location_label, map_x, map_y, active, created_at, updated_at, lat, lng;
                    """,
                    (camera_key, camera_key, map_x, map_y, location_label),
                )
                return cursor.fetchone()

        return _camera_row_to_dict(self._run(_do))

    def set_camera_location(self, camera_key, lat, lng, location_label=None, org_id=None):
        """Posição real (latitude/longitude) da câmera no mapa. Com `org_id`, só
        atualiza câmera da própria organização."""
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE cameras
                    SET lat = %s, lng = %s, location_label = COALESCE(%s, location_label), updated_at = NOW()
                    WHERE camera_key = %s AND (%s::int IS NULL OR org_id = %s::int)
                    RETURNING id, name, camera_key, location_label, map_x, map_y, active, created_at, updated_at, lat, lng;
                    """,
                    (lat, lng, location_label, camera_key, org_id, org_id),
                )
                return cursor.fetchone()

        return _camera_row_to_dict(self._run(_do))

    def query_events(self, event_types, since, until=None, camera_key=None, class_name=None, limit=None, org_id=None):
        clauses = ["event_type = ANY(%s)", "created_at >= %s"]
        params = [list(event_types), since]

        if org_id is not None:
            clauses.append("org_id = %s")
            params.append(org_id)

        if until is not None:
            clauses.append("created_at < %s")
            params.append(until)
        if camera_key is not None:
            clauses.append("event_data->>'camera_id' = %s")
            params.append(str(camera_key))
        if class_name is not None:
            clauses.append("event_data->>'class_name' = %s")
            params.append(class_name)

        query = f"""
            SELECT event_type, event_data, created_at
            FROM events
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at
        """
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()

        rows = self._run(_do)

        events = []
        for event_type, event_data, created_at in rows:
            record = dict(event_data or {})
            record.setdefault("type", event_type)
            record["created_at"] = created_at.isoformat()
            events.append(record)
        return events

    def has_events_since(self, since, org_id=None):
        def _do(conn):
            with conn.cursor() as cursor:
                if org_id is None:
                    cursor.execute(
                        "SELECT EXISTS(SELECT 1 FROM events WHERE created_at >= %s);",
                        (since,),
                    )
                else:
                    cursor.execute(
                        "SELECT EXISTS(SELECT 1 FROM events WHERE created_at >= %s AND org_id = %s);",
                        (since, org_id),
                    )
                return bool(cursor.fetchone()[0])

        return self._run(_do)

    def clear_statistics(self, org_id=None):
        """Zera o histórico de estatísticas (detecções, tracks, eventos).

        Não apaga câmeras, classes, modelos nem datasets - só os dados que
        alimentam contagens/fluxo/relatórios. Com `org_id`, apaga apenas os
        dados daquela organização; sem ele, zera tudo (uso local/demonstração).
        """
        def _do(conn):
            with conn.cursor() as cursor:
                if org_id is None:
                    cursor.execute("TRUNCATE TABLE detections, tracks, events RESTART IDENTITY;")
                else:
                    for table in ("detections", "tracks", "events"):
                        cursor.execute(f"DELETE FROM {table} WHERE org_id = %s;", (org_id,))

        self._run(_do)


class ResilientDatabase:
    """Mantém a visão funcionando quando o PostgreSQL local está indisponível.

    Eventos já são gravados em JSONL antes de chegar a esta camada. Assim, uma
    configuração de banco ausente não pode interromper câmera, YOLO ou tracking.
    """

    def __init__(self, database):
        self.database = database
        self.error = None

    def _call(self, method, *args, **kwargs):
        try:
            return getattr(self.database, method)(*args, **kwargs)
        except Exception as error:
            self.error = str(error)
            return None

    def test_connection(self):
        return self._call("test_connection")

    def initialize(self):
        return self._call("initialize")

    def seed_classes(self):
        return self._call("seed_classes")

    def record_event(self, event):
        return self._call("record_event", event)

    def record_detection(self, detection, frame_shape=None, org_id=None):
        return self._call("record_detection", detection, frame_shape, org_id)

    def record_track(self, detection, org_id=None):
        return self._call("record_track", detection, org_id)

    def summary(self):
        result = self._call("summary")
        if result is not None:
            return result
        return {
            "status": "offline",
            "backend": "postgres",
            "detail": self.error,
        }

    def upsert_camera(self, camera_key, name, source=None, org_id=None):
        return self._call("upsert_camera", camera_key, name, source, org_id)

    def deactivate_camera(self, camera_key):
        return self._call("deactivate_camera", camera_key)

    def list_cameras(self, include_inactive=False, org_id=None):
        result = self._call("list_cameras", include_inactive, org_id)
        return result if result is not None else []

    def set_camera_position(self, camera_key, map_x, map_y, location_label=None):
        return self._call("set_camera_position", camera_key, map_x, map_y, location_label)

    def set_camera_location(self, camera_key, lat, lng, location_label=None, org_id=None):
        return self._call("set_camera_location", camera_key, lat, lng, location_label, org_id)

    def query_events(self, event_types, since, until=None, camera_key=None, class_name=None, limit=None, org_id=None):
        result = self._call("query_events", event_types, since, until, camera_key, class_name, limit, org_id)
        return result if result is not None else []

    def has_events_since(self, since, org_id=None):
        result = self._call("has_events_since", since, org_id)
        return bool(result)

    def clear_statistics(self, org_id=None):
        return self._call("clear_statistics", org_id)


def create_database():
    backend = os.getenv("DATABASE_BACKEND", "").lower()

    if backend == "postgres":
        return ResilientDatabase(PostgresDatabase())

    return NullDatabase()
