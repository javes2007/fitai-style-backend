import json
import os
from flask import Blueprint, jsonify, request

from backend.security import limiter

firebase_auth_bp = Blueprint("firebase_auth", __name__)
_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    service_file = os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE")
    service_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not service_file and not service_json:
        raise RuntimeError("Firebase Admin no está configurado.")

    import firebase_admin
    from firebase_admin import credentials
    cred = credentials.Certificate(service_file) if service_file else credentials.Certificate(json.loads(service_json))
    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app


@firebase_auth_bp.route("/auth/firebase", methods=["POST"])
@limiter.limit("10 per minute")
def sincronizar_firebase():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON válido."}), 400
    id_token = data.get("id_token", "")
    if not isinstance(id_token, str) or not id_token.strip() or len(id_token) > 10000:
        return jsonify({"error": "Falta un token de Firebase válido."}), 400

    try:
        from firebase_admin import auth as firebase_auth
        _get_firebase_app()
        decoded = firebase_auth.verify_id_token(id_token.strip(), check_revoked=True)
    except Exception:
        return jsonify({"error": "El token de Firebase no es válido o Firebase Admin no está configurado."}), 401

    uid = decoded.get("uid")
    email = (decoded.get("email") or "").strip().lower()
    nombre = (decoded.get("name") or email.split("@")[0] or "Usuario").strip()
    if not uid or not email:
        return jsonify({"error": "La cuenta de Firebase no contiene identidad suficiente."}), 400

    from backend.models.usuario import Usuario
    from backend.auth.tokens import generar_token
    try:
        usuario = Usuario.obtener_por_email(email)
        if usuario:
            id_usuario = usuario["id_usuario"]
        else:
            id_usuario = Usuario.crear(nombre[:100], email, os.urandom(24).hex())
    except Exception:
        return jsonify({"error": "No se pudo sincronizar la cuenta con FitAI."}), 500

    return jsonify({
        "success": True,
        "token": generar_token(id_usuario),
        "usuario": {
            "id_usuario": id_usuario,
            "nombre": nombre[:100],
            "email": email,
            "firebase_uid": uid
        }
    }), 200
