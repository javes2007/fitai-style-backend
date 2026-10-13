from flask import Blueprint, request, jsonify, g
from backend.auth.register import procesar_registro
from backend.auth.login import procesar_login
from backend.auth.tokens import requiere_autenticacion
from backend.security import limiter
from backend.models.usuario import Usuario

usuarios_bp = Blueprint("usuarios", __name__)


def _json_object():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


@usuarios_bp.route("/register", methods=["POST"])
@limiter.limit("3 per hour")
def register():
    """Registra una cuenta tras validar estrictamente el JSON."""
    data = _json_object()
    if data is None:
        return jsonify({"success": False, "error": "El cuerpo debe ser un objeto JSON válido."}), 400

    nombre = data.get("nombre", "")
    email = data.get("email", "")
    contrasena = data.get("contrasena", "")
    if not all(isinstance(v, str) for v in (nombre, email, contrasena)):
        return jsonify({"success": False, "error": "Los campos deben ser texto válido."}), 400

    nombre = nombre.strip()
    email = email.strip()
    if not nombre and email:
        nombre = email.split("@")[0]
    response, status_code = procesar_registro(nombre, email, contrasena)
    return jsonify(response), status_code


@usuarios_bp.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
@limiter.limit("20 per hour")
def login():
    """Autentica una cuenta y limita intentos repetidos."""
    data = _json_object()
    if data is None:
        return jsonify({"success": False, "error": "El cuerpo debe ser un objeto JSON válido."}), 400

    email = data.get("email", "")
    contrasena = data.get("contrasena", "")
    if not isinstance(email, str) or not isinstance(contrasena, str):
        return jsonify({"success": False, "error": "Correo o contraseña incorrectos."}), 400

    response, status_code = procesar_login(email.strip(), contrasena)
    return jsonify(response), status_code


@usuarios_bp.route("/usuarios/me", methods=["GET"])
@requiere_autenticacion
def mi_perfil():
    """Devuelve únicamente el perfil de la identidad del token."""
    usuario = Usuario.obtener_por_id(g.id_usuario)
    if not usuario:
        return jsonify({"error": "Usuario no encontrado."}), 404

    campos = ("id_usuario", "nombre", "email", "altura", "ancho_hombros", "pecho", "cintura", "cadera")
    perfil = {campo: usuario.get(campo) for campo in campos if campo in usuario}
    perfil["autenticado"] = True
    return jsonify({"usuario": perfil}), 200


@usuarios_bp.route("/usuarios/<int:id_usuario>/medidas", methods=["PUT"])
@requiere_autenticacion
@limiter.limit("30 per hour")
def actualizar_medidas(id_usuario):
    """Actualiza medidas solo para el usuario autenticado."""
    if g.id_usuario != id_usuario:
        return jsonify({"error": "No puedes modificar los datos de otro usuario."}), 403

    data = _json_object()
    if data is None:
        return jsonify({"error": "El cuerpo debe ser un objeto JSON válido."}), 400

    campos = ("altura", "ancho_hombros", "pecho", "cintura", "cadera")
    if any(campo not in data for campo in campos):
        return jsonify({"error": "Todas las medidas corporales son obligatorias."}), 400
    try:
        medidas = [float(data[campo]) for campo in campos]
    except (TypeError, ValueError, OverflowError):
        return jsonify({"error": "Las medidas deben ser valores numéricos."}), 400

    altura, ancho_hombros, pecho, cintura, cadera = medidas
    if not (100 <= altura <= 250):
        return jsonify({"error": "La altura debe estar entre 100 y 250 cm."}), 400
    if not all(20 <= valor <= 250 for valor in (ancho_hombros, pecho, cintura, cadera)):
        return jsonify({"error": "Las medidas corporales están fuera de un rango válido."}), 400

    exito = Usuario.actualizar_medidas(id_usuario, altura, ancho_hombros, pecho, cintura, cadera)
    if exito:
        return jsonify({"mensaje": "Medidas de avatar actualizadas correctamente en la base de datos."}), 200
    return jsonify({"error": "No se pudo actualizar el registro en la base de datos."}), 500
