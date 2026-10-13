from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import os
import re
import sys
import types

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# El repositorio contiene el backend en su propia raíz, pero el código
# histórico importa los módulos con el prefijo "backend.". Registramos
# esta raíz como un paquete compatible para desarrollo y Render.
_backend_root = os.path.dirname(os.path.abspath(__file__))
if "backend" not in sys.modules:
    _backend_package = types.ModuleType("backend")
    _backend_package.__path__ = [_backend_root]
    _backend_package.__package__ = "backend"
    sys.modules["backend"] = _backend_package

from backend.config import Config
from backend.security import limiter, configurar_seguridad
from backend.database.conexion import obtener_conexion
from backend.routes.usuarios import usuarios_bp
from backend.routes.firebase_auth import firebase_auth_bp
from backend.routes.avatar import avatar_bp
from backend.routes.ropa import ropa_bp
from backend.routes.ropa_3d import ropa_3d_bp
from backend.routes.outfits import outfits_bp
from backend.routes.ia import ia_bp
from backend.routes.asistente import asistente_bp
from backend.routes.externos import externos_bp
from backend.routes.compras import compras_bp

app = Flask(__name__)
app.config.from_object(Config)
limiter.init_app(app)
configurar_seguridad(app)

# En producción define FRONTEND_ORIGINS con los dominios HTTPS exactos.
# No se habilita "null" ni file://.
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": Config.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Type", "Retry-After", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
            "max_age": 600,
        }
    }
)

app.register_blueprint(usuarios_bp, url_prefix="/api")
app.register_blueprint(firebase_auth_bp, url_prefix="/api")
app.register_blueprint(avatar_bp, url_prefix="/api")
app.register_blueprint(ropa_bp, url_prefix="/api")
app.register_blueprint(ropa_3d_bp, url_prefix="/api")
app.register_blueprint(outfits_bp, url_prefix="/api")
app.register_blueprint(ia_bp, url_prefix="/api")
app.register_blueprint(asistente_bp, url_prefix="/api")
app.register_blueprint(externos_bp, url_prefix="/api")
app.register_blueprint(compras_bp, url_prefix="/api")


@app.route("/")
def inicio():
    return jsonify({
        "proyecto": "FitAI Style API",
        "estado": "Servidor funcionando",
        "version": "2.1.0",
        "mensaje": "Backend unificado de FitAI Style"
    })


@app.route("/health")
def health():
    return jsonify({"status": "ok", "backend": True}), 200


@app.route("/status")
def status():
    db_status = False
    db_conn = None
    try:
        db_conn = obtener_conexion()
        if db_conn:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_status = True
    except Exception as exc:
        app.logger.warning("Comprobación de base de datos fallida: %s", type(exc).__name__)
    finally:
        if db_conn:
            try:
                db_conn.close()
            except Exception:
                app.logger.warning("No se pudo devolver la conexión al pool.")

    return jsonify({
        "status": "online",
        "backend": True,
        "database": db_status,
        "services": {
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "google_search": bool(os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_CSE_ID")),
            "weather": bool(os.environ.get("OPENWEATHER_API_KEY"))
        }
    }), 200


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"status": "error", "error": "El archivo o la solicitud supera el tamaño máximo permitido."}), 413


@app.errorhandler(429)
def too_many_requests(_error):
    return jsonify({"status": "error", "error": "Demasiadas solicitudes. Espera un momento antes de volver a intentarlo."}), 429


@app.route("/api/contacto", methods=["POST"])
@limiter.limit("3 per hour")
def procesar_contacto():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON válido."}), 400

    nombre = str(data.get("nombre", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    asunto = str(data.get("asunto", "")).strip()
    mensaje = str(data.get("mensaje", "")).strip()

    if not all([nombre, email, asunto, mensaje]):
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    if len(nombre) > 100 or len(email) > 254 or len(asunto) > 150 or len(mensaje) > 5000:
        return jsonify({"error": "Uno de los campos supera el tamaño permitido."}), 400
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", email):
        return jsonify({"error": "El correo electrónico no es válido."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "No se pudo conectar con la base de datos."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """INSERT INTO contactos (nombre, email, asunto, mensaje)
                   VALUES (%s, %s, %s, %s)""",
                (nombre, email, asunto, mensaje)
            )
        conn.commit()
        return jsonify({"status": "success", "mensaje": "Mensaje recibido correctamente."}), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Error guardando contacto")
        return jsonify({"error": "No se pudo guardar el mensaje."}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=Config.DEBUG)  # nosec B104: required by the container platform
