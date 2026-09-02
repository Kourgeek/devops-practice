"""
Secman — Security Manager
Flask-приложение для управления секретами с шифрованием и аудитом.
"""

import os
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from functools import wraps

import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, g, render_template, url_for
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet

from config import Config

# ---------------------------------------------------------------------------
# Логирование
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if Config.DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("secman")

# ---------------------------------------------------------------------------
# Инициализация приложения
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY

DATABASE_URL = Config.get_database_url()
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

fernet = Fernet(Config.ENCRYPTION_KEY)


# ---------------------------------------------------------------------------
# Вспомогательные функции шифрования
# ---------------------------------------------------------------------------
def encrypt_value(value: str) -> str:
    """Шифрует строку и возвращает base64-строку."""
    encrypted = fernet.encrypt(value.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_value(encrypted_value: str) -> str:
    """Дешифрует base64-строку."""
    decrypted = fernet.decrypt(encrypted_value.encode("utf-8"))
    return decrypted.decode("utf-8")


# ---------------------------------------------------------------------------
# Инициализация БД (создание таблиц если не существуют)
# ---------------------------------------------------------------------------
def init_db():
    """Создаёт таблицы, если они ещё не существуют."""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS secrets (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                key_name    VARCHAR(512) NOT NULL,
                value       TEXT         NOT NULL,
                description TEXT,
                created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          BIGSERIAL PRIMARY KEY,
                action      VARCHAR(50)  NOT NULL,
                resource    VARCHAR(255),
                resource_id VARCHAR(255),
                details     JSONB,
                ip_address  VARCHAR(45),
                created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                username     VARCHAR(255) UNIQUE NOT NULL,
                password_hash TEXT         NOT NULL,
                created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
            );
        """))
        conn.commit()

    # Создаём дефолтного пользователя, если его нет
    _ensure_default_user()


def _ensure_default_user():
    """Создаёт дефолтного админа, если таблица users пуста."""
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
        if count == 0:
            default_username = os.environ.get("SECMAN_DEFAULT_USER", "admin")
            default_password = os.environ.get("SECMAN_DEFAULT_PASSWORD", "admin123")
            pw_hash = generate_password_hash(default_password)
            conn.execute(text("""
                INSERT INTO users (username, password_hash)
                VALUES (:username, :password_hash)
            """), {"username": default_username, "password_hash": pw_hash})
            conn.commit()
            logger.info(f"Создан дефолтный пользователь: {default_username} / {default_password}")


# ---------------------------------------------------------------------------
# Middleware: сессия БД и аудит
# ---------------------------------------------------------------------------
@app.before_request
def before_request():
    g.db = SessionLocal()


@app.teardown_appcontext
def shutdown_session(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def log_audit(action: str, resource: str = None, resource_id: str = None, details: dict = None):
    """Записывает запись в аудит."""
    try:
        extra = {}
        if hasattr(g, "current_username") and g.current_username:
            extra["username"] = g.current_username
        g.db.execute(text("""
            INSERT INTO audit_log (action, resource, resource_id, details, ip_address)
            VALUES (:action, :resource, :resource_id, :details, :ip)
        """), {
            "action": action,
            "resource": resource,
            "resource_id": resource_id or "",
            "details": json.dumps(details or {}) if details else None,
            "ip": request.remote_addr or "unknown",
        })
        g.db.commit()
    except Exception as e:
        logger.error(f"Ошибка записи в аудит: {e}")


# ---------------------------------------------------------------------------
# JWT-хелперы
# ---------------------------------------------------------------------------
JWT_SECRET = os.environ.get("SECMAN_JWT_SECRET", Config.SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def _create_token(user_id: str, username: str) -> str:
    """Создаёт JWT-токен."""
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict | None:
    """Декодирует JWT-токен. Возвращает payload или None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# Декоратор require_auth
# ---------------------------------------------------------------------------
def require_auth(f):
    """Декоратор для защиты endpoint'ов JWT-аутентификацией."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Authorization header missing or invalid format. Use: Bearer <token>"}), 401

        token = auth_header[7:]  # strip "Bearer "
        payload = _decode_token(token)
        if payload is None:
            return jsonify({"error": "Invalid or expired token"}), 401

        # Получаем username из токена и кладем в g для последующего использования
        g.current_user_id = payload["user_id"]
        g.current_username = payload["username"]
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Обработчики ошибок
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Resource not found", "status": 404}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Internal server error", "status": 500}), 500


# ---------------------------------------------------------------------------
# Веб-интерфейс (UI)
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    """Редирект на UI."""
    return render_template("login.html")


@app.route("/login", methods=["GET"])
def login_page():
    """Страница логина."""
    return render_template("login.html")


@app.route("/register", methods=["GET"])
def register_page():
    """Страница регистрации."""
    return render_template("register.html")


@app.route("/dashboard")
def dashboard_page():
    """Основная страница UI (требует аутентификации)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return render_template("login.html"), 401

    token = auth_header[7:]
    payload = _decode_token(token)
    if payload is None:
        return render_template("login.html"), 401

    return render_template("dashboard.html", username=payload["username"])


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health_check():
    """Проверка работоспособности сервиса."""
    return jsonify({
        "status": "healthy",
        "service": "secman",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }), 200


# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    """Регистрация нового пользователя."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    if len(username) < 3 or len(username) > 255:
        return jsonify({"error": "Username must be between 3 and 255 characters"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    pw_hash = generate_password_hash(password)

    try:
        g.db.execute(text("""
            INSERT INTO users (username, password_hash)
            VALUES (:username, :password_hash)
        """), {"username": username, "password_hash": pw_hash})
        g.db.commit()

        log_audit("REGISTER", "user", None, {"username": username})

        return jsonify({"message": "User registered successfully", "username": username}), 201
    except Exception as e:
        g.db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return jsonify({"error": f"Username '{username}' is already taken"}), 409
        logger.error(f"Ошибка регистрации: {e}")
        return jsonify({"error": "Failed to register user"}), 500


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """Логин пользователя. Возвращает JWT-токен."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    try:
        result = g.db.execute(text("""
            SELECT id, username, password_hash FROM users WHERE username = :username
        """), {"username": username}).fetchone()

        if not result:
            log_audit("LOGIN_FAILED", "user", None, {"username": username})
            return jsonify({"error": "Invalid credentials"}), 401

        user_id, stored_username, pw_hash = result
        if not check_password_hash(pw_hash, password):
            log_audit("LOGIN_FAILED", "user", str(user_id), {"username": username})
            return jsonify({"error": "Invalid credentials"}), 401

        token = _create_token(str(user_id), stored_username)

        log_audit("LOGIN", "user", str(user_id), {"username": stored_username})

        return jsonify({
            "message": "Login successful",
            "token": token,
            "username": stored_username,
        }), 200
    except Exception as e:
        logger.error(f"Ошибка логина: {e}")
        return jsonify({"error": "Login failed"}), 500


@app.route("/api/auth/me", methods=["GET"])
@require_auth
def auth_me():
    """Информация о текущем пользователе (требует JWT)."""
    return jsonify({
        "user_id": g.current_user_id,
        "username": g.current_username,
    }), 200


# ---------------------------------------------------------------------------
# Secrets CRUD
# ---------------------------------------------------------------------------
@app.route("/api/secrets", methods=["POST"])
@require_auth
def create_secret():
    """Создать новый секрет."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required", "status": 400}), 400

    key_name = data.get("key_name", "").strip()
    value = data.get("value", "").strip()
    description = data.get("description", "")

    if not key_name or not value:
        return jsonify({"error": "key_name and value are required"}), 400

    encrypted_value = encrypt_value(value)
    secret_id = str(uuid.uuid4())

    try:
        g.db.execute(text("""
            INSERT INTO secrets (id, key_name, value, description, created_at, updated_at)
            VALUES (:id, :key_name, :value, :description, NOW(), NOW())
        """), {
            "id": secret_id,
            "key_name": key_name,
            "value": encrypted_value,
            "description": description,
        })
        g.db.commit()

        log_audit("CREATE", "secret", secret_id, {"key_name": key_name})

        return jsonify({
            "id": secret_id,
            "key_name": key_name,
            "description": description,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }), 201
    except Exception as e:
        g.db.rollback()
        logger.error(f"Ошибка создания секрета: {e}")
        return jsonify({"error": "Failed to create secret"}), 500


@app.route("/api/secrets", methods=["GET"])
@require_auth
def list_secrets():
    """Получить список всех секретов (без расшифровки значений)."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page

    try:
        result = g.db.execute(text("""
            SELECT id, key_name, description, created_at, updated_at
            FROM secrets
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": per_page, "offset": offset})

        rows = result.fetchall()
        secrets = []
        for row in rows:
            secrets.append({
                "id": row[0],
                "key_name": row[1],
                "description": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
                "updated_at": row[4].isoformat() if row[4] else None,
            })

        total = g.db.execute(text("SELECT COUNT(*) FROM secrets")).fetchone()[0]

        log_audit("LIST", "secrets")

        return jsonify({
            "secrets": secrets,
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": offset + per_page < total,
        }), 200
    except Exception as e:
        logger.error(f"Ошибка получения списка секретов: {e}")
        return jsonify({"error": "Failed to list secrets"}), 500


@app.route("/api/secrets/<secret_id>", methods=["GET"])
@require_auth
def get_secret(secret_id):
    """Получить один секрет (значение в зашифрованном виде)."""
    try:
        result = g.db.execute(text("""
            SELECT id, key_name, value, description, created_at, updated_at
            FROM secrets
            WHERE id = :id
        """), {"id": secret_id})

        row = result.fetchone()
        if not row:
            return jsonify({"error": "Secret not found"}), 404

        log_audit("READ", "secret", secret_id)

        return jsonify({
            "id": row[0],
            "key_name": row[1],
            "value": row[2],
            "description": row[3],
            "encrypted": True,
            "created_at": row[4].isoformat() if row[4] else None,
            "updated_at": row[5].isoformat() if row[5] else None,
        }), 200
    except Exception as e:
        logger.error(f"Ошибка получения секрета: {e}")
        return jsonify({"error": "Failed to get secret"}), 500


@app.route("/api/secrets/<secret_id>", methods=["PUT"])
@require_auth
def update_secret(secret_id):
    """Обновить секрет."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required", "status": 400}), 400

    try:
        existing = g.db.execute(text("SELECT id FROM secrets WHERE id = :id"), {"id": secret_id}).fetchone()
        if not existing:
            return jsonify({"error": "Secret not found"}), 404

        updates = []
        params = {"id": secret_id}

        if "key_name" in data:
            updates.append("key_name = :key_name")
            params["key_name"] = data["key_name"].strip()
        if "value" in data:
            updates.append("value = :value")
            params["value"] = encrypt_value(data["value"].strip())
        if "description" in data:
            updates.append("description = :description")
            params["description"] = data["description"]

        if not updates:
            return jsonify({"error": "No fields to update"}), 400

        updates.append("updated_at = NOW()")

        g.db.execute(text(f"""
            UPDATE secrets SET {', '.join(updates)}
            WHERE id = :id
        """), params)
        g.db.commit()

        log_audit("UPDATE", "secret", secret_id)

        return jsonify({"message": "Secret updated", "id": secret_id}), 200
    except Exception as e:
        g.db.rollback()
        logger.error(f"Ошибка обновления секрета: {e}")
        return jsonify({"error": "Failed to update secret"}), 500


@app.route("/api/secrets/<secret_id>", methods=["DELETE"])
@require_auth
def delete_secret(secret_id):
    """Удалить секрет."""
    try:
        existing = g.db.execute(text("SELECT id FROM secrets WHERE id = :id"), {"id": secret_id}).fetchone()
        if not existing:
            return jsonify({"error": "Secret not found"}), 404

        g.db.execute(text("DELETE FROM secrets WHERE id = :id"), {"id": secret_id})
        g.db.commit()

        log_audit("DELETE", "secret", secret_id)

        return jsonify({"message": "Secret deleted", "id": secret_id}), 200
    except Exception as e:
        g.db.rollback()
        logger.error(f"Ошибка удаления секрета: {e}")
        return jsonify({"error": "Failed to delete secret"}), 500


# ---------------------------------------------------------------------------
# Импорт из Jenkins
# ---------------------------------------------------------------------------
@app.route("/api/secrets/import", methods=["POST"])
@require_auth
def import_from_jenkins():
    """
    Импортировать секреты из Jenkins Credentials.
    Ожидается JSON body:
    {
        "credentials": [
            {"id": "cred-1", "username": "user", "password": "pass", "description": "desc"},
            ...
        ]
    }
    """
    data = request.get_json()
    if not data or "credentials" not in data:
        return jsonify({"error": "credentials array is required"}), 400

    credentials = data["credentials"]
    if not isinstance(credentials, list):
        return jsonify({"error": "credentials must be an array"}), 400

    imported = 0
    errors = []

    for cred in credentials:
        try:
            secret_id = str(uuid.uuid4())
            key_name = cred.get("id", f"jenkins-{imported}")
            username = cred.get("username", "")
            password = cred.get("password", "")
            description = cred.get("description", f"Imported from Jenkins ({key_name})")

            # Храним username:password как единое значение
            combined_value = f"{username}:{password}"
            encrypted_value = encrypt_value(combined_value)

            g.db.execute(text("""
                INSERT INTO secrets (id, key_name, value, description, created_at, updated_at)
                VALUES (:id, :key_name, :value, :description, NOW(), NOW())
            """), {
                "id": secret_id,
                "key_name": key_name,
                "value": encrypted_value,
                "description": description,
            })
            imported += 1
        except Exception as e:
            logger.error(f"Ошибка импорта секрета {cred.get('id', '?')}: {e}")
            errors.append({"id": cred.get("id", "unknown"), "error": str(e)})

    g.db.commit()

    log_audit("IMPORT", "secrets", details={"imported": imported, "errors": len(errors)})

    return jsonify({
        "message": f"Imported {imported} secrets from Jenkins",
        "imported": imported,
        "errors": errors,
    }), 201 if imported else 400


# ---------------------------------------------------------------------------
# Аудит
# ---------------------------------------------------------------------------
@app.route("/api/audit", methods=["GET"])
@require_auth
def get_audit_log():
    """Получить журнал аудита."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(per_page, 200)
    offset = (page - 1) * per_page
    action_filter = request.args.get("action", None)

    try:
        query = """
            SELECT id, action, resource, resource_id, details, ip_address, created_at
            FROM audit_log
        """
        params: dict = {"limit": per_page, "offset": offset}

        if action_filter:
            query += " WHERE action = :action"
            params["action"] = action_filter

        query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

        result = g.db.execute(text(query), params)
        rows = result.fetchall()

        total_query = "SELECT COUNT(*) FROM audit_log"
        if action_filter:
            total_query += " WHERE action = :action"
        total = g.db.execute(text(total_query), params).fetchone()[0]

        audit_entries = []
        for row in rows:
            details = None
            if row[4]:
                try:
                    details = json.loads(row[4])
                except (json.JSONDecodeError, TypeError):
                    details = row[4]

            audit_entries.append({
                "id": row[0],
                "action": row[1],
                "resource": row[2],
                "resource_id": row[3],
                "details": details,
                "ip_address": row[5],
                "created_at": row[6].isoformat() if row[6] else None,
            })

        return jsonify({
            "audit_log": audit_entries,
            "total": total,
            "page": page,
            "per_page": per_page,
            "has_next": offset + per_page < total,
        }), 200
    except Exception as e:
        logger.error(f"Ошибка получения аудита: {e}")
        return jsonify({"error": "Failed to get audit log"}), 500


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    logger.info("Secman starting in development mode")
    app.run(host="0.0.0.0", port=9090, debug=Config.DEBUG)
else:
    init_db()
