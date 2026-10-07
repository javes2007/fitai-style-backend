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
# esta raíz como un paquete compatible para que ambos entornos funcionen:
# desarrollo local y despliegue en Render.
_backend_root = os.path.dirname(os.path.abspath(__file__))
if "backend" not in sys.modules:
    _backend_package = types.ModuleType("backend")
    _backend_package.__path__ = [_backend_root]
    _backend_package.__package__ = "backend"
    sys.modules["backend"] = _backend_package

from backend.config import Config
from backend.database.conexion import obtener_conexion
from backend.routes.usuarios import usuarios_bp
from backend.routes.firebase_auth import firebase_auth_bp
from backend.routes.avatar import avatar_bp
from backend.routes.ropa import ropa_bp
from backend.routes.outfits import outfits_bp
from backend.routes.ia import ia_bp
from backend.routes.asistente import asistente_bp
from backend.routes.externos import externos_bp

app = Flask(__name__)
app.config.from_object(Config)

# En desarrollo, sin FRONTEND_ORIGINS, permitimos el frontend local.
cors_origins = Config.CORS_ORIGINS or [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "null",  # abrir HTML con file:// (solo desarrollo)
]
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": cors_origins,
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Type"],
            "max_age": 600,
        }
    }
)

app.register_blueprint(usuarios_bp, url_prefix="/api")
app.register_blueprint(firebase_auth_bp, url_prefix="/api")
app.register_blueprint(avatar_bp, url_prefix="/api")
app.register_blueprint(ropa_bp, url_prefix="/api")
app.register_blueprint(outfits_bp, url_prefix="/api")
app.register_blueprint(ia_bp, url_prefix="/api")
app.register_blueprint(asistente_bp, url_prefix="/api")
app.register_blueprint(externos_bp, url_prefix="/api")


@app.route("/")
def inicio():
    return jsonify({
        "proyecto": "FitAI Style API",
        "estado": "Servidor funcionando",
        "version": "2.0.0",
        "mensaje": "Backend unificado de FitAI Style"
    })


@app.route("/status")
def status():
    db_conn = obtener_conexion()
    db_status = False
    if db_conn:
        try:
            with db_conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            db_status = True
        finally:
            db_conn.close()

    return jsonify({
        "status": "online",
        "backend": True,
        "database": db_status,
        "services": {
            "gemini": bool(os.environ.get("GEMINI_API_KEY")),
            "google_search": bool(os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_CSE_ID")),
            "weather": bool(os.environ.get("OPENWEATHER_API_KEY"))
        }
    })


@app.route("/api/contacto", methods=["POST"])
def procesar_contacto():
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    asunto = str(data.get("asunto", "")).strip()
    mensaje = str(data.get("mensaje", "")).strip()

    if not all([nombre, email, asunto, mensaje]):
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    if len(nombre) > 100 or len(asunto) > 150 or len(mensaje) > 5000:
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
        return jsonify({
            "status": "success",
            "mensaje": "Mensaje recibido correctamente."
        }), 201
    except Exception:
        conn.rollback()
        app.logger.exception("Error guardando contacto")
        return jsonify({"error": "No se pudo guardar el mensaje."}), 500
    finally:
        conn.close()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=Config.DEBUG
    )
