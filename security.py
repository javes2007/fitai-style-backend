"""Configuración común de seguridad HTTP, HTTPS y limitación de solicitudes."""
import os

from flask import request, redirect, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix

# En producción configure RATELIMIT_STORAGE_URI con Redis para compartir límites
# entre procesos/instancias. memory:// es un fallback de desarrollo.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per day", "60 per hour"],
    storage_uri=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
)


def configurar_seguridad(app):
    """Activa cabeceras defensivas, validación JSON y HTTPS en producción."""
    if not app.debug and os.environ.get("TRUST_PROXY_HEADERS", "1") == "1":
        # Render termina TLS en su proxy; confiar solo en el salto inmediato.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    @app.before_request
    def controles_entrada():
        force_https = os.environ.get("FORCE_HTTPS", "1" if os.environ.get("RENDER") else "0") == "1"
        if force_https and not app.debug and not request.is_secure:
            if request.method in {"GET", "HEAD", "OPTIONS"}:
                return redirect(request.url.replace("http://", "https://", 1), code=308)
            return jsonify({"error": "Se requiere HTTPS para esta solicitud."}), 400

        # Los endpoints JSON de la API esperan objetos; rechazar arrays,
        # escalares y JSON malformado antes de que las rutas accedan a .get().
        if request.method in {"POST", "PUT", "PATCH"} and request.path.startswith("/api/") and request.is_json:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "El cuerpo debe ser un objeto JSON válido."}), 400
        return None

    @app.after_request
    def cabeceras_seguras(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        force_https = os.environ.get("FORCE_HTTPS", "1" if os.environ.get("RENDER") else "0") == "1"
        if not app.debug and force_https and request.is_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if response.mimetype == "application/json" and request.path.startswith(
            ("/api/auth", "/api/login", "/api/register", "/api/usuarios")
        ):
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response
