import os
import secrets
import warnings

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key and os.environ.get("RENDER"):
    raise RuntimeError("SECRET_KEY debe configurarse como variable secreta en Render.")
if not _secret_key:
    _secret_key = secrets.token_hex(32)

class Config:
    SECRET_KEY = _secret_key

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "fitai_style")
    DB_PORT = int(os.environ.get("DB_PORT", 3306))

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    MAX_FORM_MEMORY_SIZE = 500 * 1024
    MAX_FORM_PARTS = 100

    AVATAR_MODEL_URL = os.environ.get(
        "AVATAR_MODEL_URL",
        "https://cdn.jsdelivr.net/gh/nirholas/three.ws@5c7d87a768152cd64a8cce2feef8831411062eb5/public/avatars/parametric-base.glb",
    )

    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    _default_cors_origins = [
        "https://fitai-style-frontend.vercel.app",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
    ]
    _cors_env = [origin.strip() for origin in os.environ.get("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
    if os.environ.get("RENDER"):
        production_origins = _cors_env or [origin for origin in _default_cors_origins if origin.startswith("https://")]
        CORS_ORIGINS = list(dict.fromkeys(origin for origin in production_origins if origin.startswith("https://")))
    else:
        CORS_ORIGINS = list(dict.fromkeys(_default_cors_origins + _cors_env))

if not os.environ.get("DB_PASSWORD"):
    warnings.warn("DB_PASSWORD no está definida. Configúrala antes de desplegar.", stacklevel=2)

if not os.environ.get("SECRET_KEY"):
    warnings.warn("SECRET_KEY no está definida; se generó una clave temporal para desarrollo.", stacklevel=2)
