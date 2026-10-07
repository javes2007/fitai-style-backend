import json
import os
from flask import Blueprint, jsonify, request

firebase_auth_bp = Blueprint("firebase_auth", __name__)

_firebase_app = None

def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app

    service_file = os.environ.get("FIREBASE_SERVICE_ACCOUNT_FILE")
    service_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not service_file and not service_json:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT_FILE o FIREBASE_SERVICE_ACCOUNT_JSON no está configurado.")

    import firebase_admin
    from firebase_admin import credentials

    if service_file:
        cred = credentials.Certificate(service_file)
    else:
        cred = credentials.Certificate(json.loads(service_json))

    _firebase_app = firebase_admin.initialize_app(cred)
    return _firebase_app

@firebase_auth_bp.route("/auth/firebase", methods=["POST"])
def sincronizar_firebase():
    data = request.get_json(silent=True) or {}
    id_token = str(data.get("id_token", "")).strip()
    if not id_token:
        return jsonify({"error":"Falta el token de Firebase."}),400

    try:
        from firebase_admin import auth as firebase_auth
        _get_firebase_app()
        decoded = firebase_auth.verify_id_token(id_token)
    except Exception:
        return jsonify({"error":"El token de Firebase no es válido o Firebase Admin no está configurado."}),401

    uid = decoded.get("uid")
    email = (decoded.get("email") or "").strip().lower()
    nombre = (decoded.get("name") or email.split("@")[0] or "Usuario").strip()

    if not uid or not email:
        return jsonify({"error":"La cuenta de Firebase no contiene un correo verificable."}),400

    from backend.models.usuario import Usuario
    from backend.auth.tokens import generar_token

    try:
        usuario = Usuario.obtener_por_email(email)
        if usuario:
            id_usuario = usuario["id_usuario"]
        else:
            id_usuario = Usuario.crear(nombre[:100], email, os.urandom(24).hex())
    except Exception:
        return jsonify({"error":"No se pudo sincronizar la cuenta con FitAI."}),500

    return jsonify({
        "success": True,
        "token": generar_token(id_usuario),
        "usuario": {
            "id_usuario": id_usuario,
            "nombre": nombre[:100],
            "email": email,
            "firebase_uid": uid
        }
    }),200
