"""Organizações, usuários e consumo de planos (PostgreSQL).

Cada organização (cliente da VIA) tem um plano, usuários e contadores de uso
mensal. Toda leitura de dados de tráfego é filtrada por `org_id` mais acima
(query_engine / dashboard); aqui ficam só contas e limites.
"""

from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from config.plans import (
    INTERNAL_ORG_NAME,
    PLANS,
    ROLES,
    ROLE_VIA_ADMIN,
    get_plan,
    within_limit,
)

MIN_PASSWORD_LENGTH = 8
_NO_LIMIT = 2**31 - 1


def validate_new_password(password, email=""):
    """Política mínima de senha. Levanta ValueError com mensagem em português."""
    password = password or ""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(password) > 128:
        raise ValueError("A senha pode ter no máximo 128 caracteres.")
    if password.lower() in {(email or "").lower(), (email or "").split("@")[0].lower()}:
        raise ValueError("A senha não pode ser igual ao seu e-mail.")
    if len(set(password)) < 4:
        raise ValueError("Escolha uma senha menos repetitiva.")


def current_period(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime("%Y-%m")


def normalize_email(email):
    return (email or "").strip().lower()


def org_status(org, now=None):
    """'active', 'inactive' (suspensa pela VIA) ou 'expired' (plano vencido)."""
    if not org["active"]:
        return "inactive"
    expires = org.get("plan_expires_at")
    if expires is not None:
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires)
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= (now or datetime.now(timezone.utc)):
            return "expired"
    return "active"


def _org_row(row):
    if row is None:
        return None
    org_id, name, plan, active, expires, created_at = row
    return {
        "id": org_id,
        "name": name,
        "plan": plan,
        "active": active,
        "plan_expires_at": expires.isoformat() if expires else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


def _user_row(row):
    if row is None:
        return None
    user_id, org_id, email, name, role, active, created_at, last_login = row
    return {
        "id": user_id,
        "org_id": org_id,
        "email": email,
        "name": name,
        "role": role,
        "active": active,
        "created_at": created_at.isoformat() if created_at else None,
        "last_login_at": last_login.isoformat() if last_login else None,
    }


_ORG_COLUMNS = "id, name, plan, active, plan_expires_at, created_at"
_USER_COLUMNS = "id, org_id, email, name, role, active, created_at, last_login_at"


class AccountStore:
    """`database` é um PostgresDatabase (usa a conexão persistente dele)."""

    def __init__(self, database):
        self.database = database

    def _run(self, fn):
        return self.database._run(fn)

    # ---- schema -------------------------------------------------------

    def initialize(self):
        schema = """
        CREATE TABLE IF NOT EXISTS organizations (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            plan TEXT NOT NULL DEFAULT 'intelligence',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            plan_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            email TEXT NOT NULL UNIQUE,
            name TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login_at TIMESTAMPTZ
        );
        -- Sobe a cada troca de senha: derruba as outras sessões abertas.
        ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;
        -- Município escolhido no login (centro do mapa); código IBGE de 7 dígitos.
        ALTER TABLE users ADD COLUMN IF NOT EXISTS municipio_ibge INTEGER;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS municipio_nome TEXT;
        ALTER TABLE users ADD COLUMN IF NOT EXISTS municipio_uf TEXT;
        -- Foto de perfil: 0 = sem foto; sobe a cada troca (serve de versão para o cache do navegador).
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_version INTEGER NOT NULL DEFAULT 0;

        -- Conversas do assistente VIA: privadas de cada usuário (nem o responsável da
        -- organização lê as de outro usuário). Apagam junto com o usuário/organização.
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id BIGSERIAL PRIMARY KEY,
            org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL DEFAULT 'Nova conversa',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_conv_user ON chat_conversations (user_id, updated_at DESC);
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGSERIAL PRIMARY KEY,
            conversation_id BIGINT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            meta JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_chat_msg_conv ON chat_messages (conversation_id, id);

        CREATE TABLE IF NOT EXISTS usage_counters (
            org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            period TEXT NOT NULL,
            metric TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (org_id, period, metric)
        );
        """

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(schema)

        self._run(_do)
        internal_id = self.ensure_internal_org()
        self._backfill_legacy_data(internal_id)

    def ensure_internal_org(self):
        """Garante a organização interna (id estável) que herda os dados que
        existiam antes do multi-cliente (câmera local, eventos antigos)."""

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM organizations WHERE plan = 'interno' ORDER BY id LIMIT 1;")
                row = cursor.fetchone()
                if row:
                    return row[0]
                cursor.execute(
                    "INSERT INTO organizations (name, plan) VALUES (%s, 'interno') "
                    "ON CONFLICT (name) DO UPDATE SET plan = 'interno' RETURNING id;",
                    (INTERNAL_ORG_NAME,),
                )
                return cursor.fetchone()[0]

        return self._run(_do)

    def _backfill_legacy_data(self, internal_org_id):
        def _do(conn):
            with conn.cursor() as cursor:
                for table in ("events", "detections", "tracks", "cameras"):
                    cursor.execute(
                        f"UPDATE {table} SET org_id = %s WHERE org_id IS NULL;",
                        (internal_org_id,),
                    )

        self._run(_do)

    # ---- organizações -------------------------------------------------

    def create_org(self, name, plan, plan_expires_at=None):
        name = (name or "").strip()
        if not name:
            raise ValueError("Informe o nome da organização.")
        if plan not in PLANS:
            raise ValueError(f"Plano inválido: {plan}. Use um de: {', '.join(PLANS)}.")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO organizations (name, plan, plan_expires_at) VALUES (%s, %s, %s) "
                    f"ON CONFLICT (name) DO NOTHING RETURNING {_ORG_COLUMNS};",
                    (name, plan, plan_expires_at),
                )
                return cursor.fetchone()

        row = self._run(_do)
        if row is None:
            raise ValueError("Já existe uma organização com esse nome.")
        return _org_row(row)

    def get_org(self, org_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT {_ORG_COLUMNS} FROM organizations WHERE id = %s;", (org_id,))
                return cursor.fetchone()

        return _org_row(self._run(_do))

    def update_org(self, org_id, plan=None, active=None, plan_expires_at=..., name=None):
        """`plan_expires_at=...` (Ellipsis) mantém o valor; `None` remove o vencimento."""
        sets, params = [], []
        if plan is not None:
            if plan not in PLANS:
                raise ValueError(f"Plano inválido: {plan}. Use um de: {', '.join(PLANS)}.")
            sets.append("plan = %s")
            params.append(plan)
        if active is not None:
            sets.append("active = %s")
            params.append(bool(active))
        if plan_expires_at is not ...:
            sets.append("plan_expires_at = %s")
            params.append(plan_expires_at)
        if name is not None:
            sets.append("name = %s")
            params.append(name.strip())
        if not sets:
            return self.get_org(org_id)
        params.append(org_id)

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE organizations SET {', '.join(sets)} WHERE id = %s RETURNING {_ORG_COLUMNS};",
                    params,
                )
                return cursor.fetchone()

        return _org_row(self._run(_do))

    def list_orgs(self):
        """Organizações com contagem de usuários e uso do mês (painel /admin)."""
        period = current_period()

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT o.id, o.name, o.plan, o.active, o.plan_expires_at, o.created_at,
                           (SELECT COUNT(*) FROM users u WHERE u.org_id = o.id AND u.active),
                           COALESCE((SELECT count FROM usage_counters c
                                     WHERE c.org_id = o.id AND c.period = %s AND c.metric = 'chat'), 0),
                           COALESCE((SELECT count FROM usage_counters c
                                     WHERE c.org_id = o.id AND c.period = %s AND c.metric = 'pdf'), 0)
                    FROM organizations o ORDER BY o.id;
                    """,
                    (period, period),
                )
                return cursor.fetchall()

        orgs = []
        for row in self._run(_do):
            org = _org_row(row[:6])
            org["status"] = org_status(org)
            org["users"] = row[6]
            org["usage"] = {"chat": row[7], "pdf": row[8], "period": period}
            orgs.append(org)
        return orgs

    # ---- usuários -----------------------------------------------------

    def count_active_users(self, org_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM users WHERE org_id = %s AND active;", (org_id,))
                return cursor.fetchone()[0]

        return self._run(_do)

    def create_user(self, org_id, email, password, role="member", name=None):
        email = normalize_email(email)
        if "@" not in email:
            raise ValueError("E-mail inválido.")
        validate_new_password(password, email)
        if role not in ROLES:
            raise ValueError(f"Papel inválido: {role}.")

        org = self.get_org(org_id)
        if org is None:
            raise ValueError("Organização não encontrada.")
        if not within_limit(get_plan(org["plan"])["max_users"], self.count_active_users(org_id)):
            raise ValueError("Limite de usuários do plano atingido.")

        password_hash = generate_password_hash(password)

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"INSERT INTO users (org_id, email, name, password_hash, role) "
                    f"VALUES (%s, %s, %s, %s, %s) ON CONFLICT (email) DO NOTHING RETURNING {_USER_COLUMNS};",
                    (org_id, email, (name or "").strip() or None, password_hash, role),
                )
                return cursor.fetchone()

        row = self._run(_do)
        if row is None:
            raise ValueError("Já existe um usuário com esse e-mail.")
        return _user_row(row)

    def list_users(self, org_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_USER_COLUMNS} FROM users WHERE org_id = %s ORDER BY email;", (org_id,)
                )
                return cursor.fetchall()

        return [_user_row(row) for row in self._run(_do)]

    def get_user(self, user_id):
        """Usuário + dados da organização, usado a cada requisição autenticada."""

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT u.id, u.org_id, u.email, u.name, u.role, u.active, u.created_at, u.last_login_at,
                           o.id, o.name, o.plan, o.active, o.plan_expires_at, o.created_at,
                           u.session_version, u.municipio_ibge, u.municipio_nome, u.municipio_uf, u.avatar_version
                    FROM users u JOIN organizations o ON o.id = u.org_id
                    WHERE u.id = %s;
                    """,
                    (user_id,),
                )
                return cursor.fetchone()

        row = self._run(_do)
        if row is None:
            return None
        user = _user_row(row[:8])
        user["org"] = _org_row(row[8:14])
        user["org"]["status"] = org_status(user["org"])
        user["session_version"] = row[14]
        user["municipio"] = (
            {"id": row[15], "nome": row[16], "uf": row[17]} if row[15] else None
        )
        user["avatar_version"] = row[18]
        return user

    def authenticate(self, email, password):
        """Devolve (user, erro). `erro` é uma mensagem pronta para o usuário."""
        email = normalize_email(email)

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, password_hash FROM users WHERE email = %s;", (email,))
                return cursor.fetchone()

        row = self._run(_do)
        # Compara contra um hash mesmo sem usuário para não revelar por tempo
        # de resposta se o e-mail existe.
        stored = row[1] if row else generate_password_hash("invalido-" + email)
        valid = check_password_hash(stored, password or "")
        if not row or not valid:
            return None, "E-mail ou senha incorretos."

        user = self.get_user(row[0])
        if not user["active"]:
            return None, "Usuário desativado. Fale com o responsável da sua organização."
        if user["role"] != ROLE_VIA_ADMIN:
            status = user["org"]["status"]
            if status == "inactive":
                return None, "Conta suspensa. Entre em contato com a VIA."
            if status == "expired":
                return None, "O plano da sua organização expirou. Entre em contato com a VIA."

        def _touch(conn):
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET last_login_at = NOW() WHERE id = %s;", (user["id"],))

        self._run(_touch)
        return user, None

    def set_user_active(self, org_id, user_id, active):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE users SET active = %s WHERE id = %s AND org_id = %s RETURNING {_USER_COLUMNS};",
                    (bool(active), user_id, org_id),
                )
                return cursor.fetchone()

        return _user_row(self._run(_do))

    def set_password(self, user_id, password):
        user = self.get_user(user_id)
        validate_new_password(password, user["email"] if user else "")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET password_hash = %s, session_version = session_version + 1 "
                    "WHERE id = %s RETURNING session_version;",
                    (generate_password_hash(password), user_id),
                )
                return cursor.fetchone()[0]

        return self._run(_do)

    def change_password(self, user_id, current_password, new_password):
        """Troca a senha exigindo a atual. Devolve a nova versão de sessão
        (a sessão de quem trocou continua válida; as demais caem)."""

        def _hash(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT password_hash, email FROM users WHERE id = %s;", (user_id,))
                return cursor.fetchone()

        row = self._run(_hash)
        if row is None or not check_password_hash(row[0], current_password or ""):
            raise ValueError("A senha atual está incorreta.")
        if check_password_hash(row[0], new_password or ""):
            raise ValueError("A nova senha precisa ser diferente da atual.")
        return self.set_password(user_id, new_password)

    def bump_avatar(self, user_id):
        """Registra uma nova foto e devolve a versão (para o cache do navegador)."""
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET avatar_version = avatar_version + 1 WHERE id = %s RETURNING avatar_version;",
                    (user_id,),
                )
                return cursor.fetchone()[0]

        return self._run(_do)

    def clear_avatar(self, user_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("UPDATE users SET avatar_version = 0 WHERE id = %s;", (user_id,))

        self._run(_do)

    def set_municipio(self, user_id, ibge_id, nome, uf):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE users SET municipio_ibge = %s, municipio_nome = %s, municipio_uf = %s WHERE id = %s;",
                    (ibge_id, nome, uf, user_id),
                )

        self._run(_do)

    def update_name(self, user_id, name):
        name = (name or "").strip()
        if len(name) > 80:
            raise ValueError("O nome pode ter no máximo 80 caracteres.")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    f"UPDATE users SET name = %s WHERE id = %s RETURNING {_USER_COLUMNS};",
                    (name or None, user_id),
                )
                return cursor.fetchone()

        return _user_row(self._run(_do))

    def has_any_user(self):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM users);")
                return cursor.fetchone()[0]

        return self._run(_do)

    # ---- conversas do assistente (sempre filtradas pelo dono) ----------

    MAX_CONVERSATIONS = 200
    MAX_MESSAGES = 400

    def chat_list(self, user_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, updated_at FROM chat_conversations WHERE user_id = %s "
                    "ORDER BY updated_at DESC, id DESC LIMIT %s;",
                    (user_id, self.MAX_CONVERSATIONS),
                )
                return cursor.fetchall()

        return [{"id": r[0], "title": r[1], "updated_at": r[2].isoformat()} for r in self._run(_do)]

    def chat_count(self, user_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM chat_conversations WHERE user_id = %s;", (user_id,))
                return cursor.fetchone()[0]

        return self._run(_do)

    def chat_create(self, org_id, user_id, title="Nova conversa"):
        if self.chat_count(user_id) >= self.MAX_CONVERSATIONS:
            raise ValueError("Limite de conversas atingido. Exclua alguma para criar outra.")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO chat_conversations (org_id, user_id, title) VALUES (%s, %s, %s) "
                    "RETURNING id, title, updated_at;",
                    (org_id, user_id, (title or "Nova conversa").strip()[:80] or "Nova conversa"),
                )
                return cursor.fetchone()

        r = self._run(_do)
        return {"id": r[0], "title": r[1], "updated_at": r[2].isoformat()}

    def chat_get(self, user_id, conv_id):
        """Conversa do usuário (None se não existe ou é de outra pessoa)."""
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, title, updated_at, (SELECT COUNT(*) FROM chat_messages m WHERE m.conversation_id = c.id) "
                    "FROM chat_conversations c WHERE id = %s AND user_id = %s;",
                    (conv_id, user_id),
                )
                return cursor.fetchone()

        r = self._run(_do)
        return None if r is None else {"id": r[0], "title": r[1], "updated_at": r[2].isoformat(), "messages": r[3]}

    def chat_messages(self, user_id, conv_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT m.id, m.role, m.content, m.meta, m.created_at FROM chat_messages m "
                    "JOIN chat_conversations c ON c.id = m.conversation_id "
                    "WHERE m.conversation_id = %s AND c.user_id = %s ORDER BY m.id LIMIT %s;",
                    (conv_id, user_id, self.MAX_MESSAGES),
                )
                return cursor.fetchall()

        out = []
        for mid, role, content, meta, created in self._run(_do):
            meta = meta or {}
            out.append({
                "id": mid, "role": role, "content": content, "created_at": created.isoformat(),
                # só o necessário para o link "baixar relatório deste período"
                "intent": meta.get("intent") if meta.get("has_data") else None,
            })
        return out

    def chat_last_intent(self, user_id, conv_id):
        """Intenção da última resposta (contexto para perguntas de acompanhamento)."""
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT m.meta FROM chat_messages m JOIN chat_conversations c ON c.id = m.conversation_id "
                    "WHERE m.conversation_id = %s AND c.user_id = %s AND m.role = 'assistant' "
                    "AND m.meta->'intent' IS NOT NULL ORDER BY m.id DESC LIMIT 1;",
                    (conv_id, user_id),
                )
                return cursor.fetchone()

        row = self._run(_do)
        return ((row[0] or {}).get("intent") if row else None)

    def chat_add(self, user_id, conv_id, role, content, meta=None):
        """Grava a mensagem só se a conversa for do usuário. Devolve None caso contrário."""
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO chat_messages (conversation_id, role, content, meta) "
                    "SELECT %s, %s, %s, %s WHERE EXISTS "
                    "(SELECT 1 FROM chat_conversations WHERE id = %s AND user_id = %s) RETURNING id;",
                    (conv_id, role, content, self.database.psycopg.types.json.Jsonb(meta) if meta else None, conv_id, user_id),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE chat_conversations SET updated_at = NOW() WHERE id = %s;", (conv_id,))
                return row

        row = self._run(_do)
        return None if row is None else {"id": row[0]}

    def chat_rename(self, user_id, conv_id, title):
        title = (title or "").strip()[:80]
        if not title:
            raise ValueError("Informe um título.")

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE chat_conversations SET title = %s WHERE id = %s AND user_id = %s RETURNING id;",
                    (title, conv_id, user_id),
                )
                return cursor.fetchone()

        return self._run(_do) is not None

    def chat_delete(self, user_id, conv_id):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM chat_conversations WHERE id = %s AND user_id = %s RETURNING id;", (conv_id, user_id))
                return cursor.fetchone()

        return self._run(_do) is not None

    # ---- consumo ------------------------------------------------------

    def usage(self, org_id, metric, period=None):
        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT count FROM usage_counters WHERE org_id = %s AND period = %s AND metric = %s;",
                    (org_id, period or current_period(), metric),
                )
                row = cursor.fetchone()
                return row[0] if row else 0

        return self._run(_do)

    def consume(self, org_id, metric, limit):
        """Consome 1 unidade do limite mensal de forma atômica.
        Devolve True se coube; False se o limite do mês já foi atingido."""
        if limit is not None and limit <= 0:
            return False

        def _do(conn):
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO usage_counters (org_id, period, metric, count)
                    VALUES (%s, %s, %s, 1)
                    ON CONFLICT (org_id, period, metric)
                    DO UPDATE SET count = usage_counters.count + 1
                    WHERE usage_counters.count < %s
                    RETURNING count;
                    """,
                    (org_id, current_period(), metric, _NO_LIMIT if limit is None else limit),
                )
                return cursor.fetchone() is not None

        return self._run(_do)
