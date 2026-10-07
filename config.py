import os
import secrets
import warnings

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "fitai_style")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "16")) * 1024 * 1024

    # Modelo humano paramétrico compartido con el frontend V5.
    AVATAR_MODEL_URL = os.environ.get(
        "AVATAR_MODEL_URL",
        "https://cdn.jsdelivr.net/gh/nirholas/three.ws@5c7d87a768152cd64a8cce2feef8831411062eb5/public/avatars/parametric-base.glb",
    )

    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    # En producción define FRONTEND_ORIGINS como una lista separada por comas.
    # Ej.: https://fitai.example.com,https://www.fitai.example.com
    CORS_ORIGINS = [
        origin.strip() for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",")
        if origin.strip()
    ]

if not os.environ.get("DB_PASSWORD"):
    warnings.warn(
        "DB_PASSWORD no está definida. Configúrala antes de desplegar.",
        stacklevel=2,
    )

if not os.environ.get("SECRET_KEY"):
    warnings.warn(
        "SECRET_KEY no está definida. Se generará una temporal; "
        "las sesiones JWT se invalidarán al reiniciar.",
        stacklevel=2,
    )
