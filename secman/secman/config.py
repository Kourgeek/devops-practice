import os
from cryptography.fernet import Fernet


def get_secret_key() -> bytes:
    """Получение ключа шифрования из переменной окружения или генерация нового."""
    secret = os.environ.get("SECMAN_SECRET_KEY", "dev-secret-key-change-in-prod")
    # Fernet требует 32-байтовый URL-safe base64-encoded key
    key = secret.encode()
    if len(key) < 32:
        key = Fernet.generate_key()
    return key


class Config:
    """Конфигурация приложения Secman."""

    # Flask
    SECRET_KEY = os.environ.get("SECMAN_SECRET_KEY", "dev-secret-key-change-in-prod")
    DEBUG = os.environ.get("SECMAN_DEBUG", "false").lower() in ("true", "1", "yes")

    # PostgreSQL
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "secman")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "secman123")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "secman_db")
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
    POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))

    DATABASE_URL = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # Encryption
    ENCRYPTION_KEY = get_secret_key()

    # Jenkins
    JENKINS_URL = os.environ.get("SECMAN_JENKINS_URL", "http://jenkins:8080")
    JENKINS_API_TOKEN = os.environ.get("SECMAN_JENKINS_API_TOKEN", "dev-token")

    @classmethod
    def get_database_url(cls) -> str:
        return cls.DATABASE_URL
