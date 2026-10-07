from flask import Blueprint, request, jsonify, g
from backend.auth.register import procesar_registro
from backend.auth.login import procesar_login
from backend.auth.tokens import requiere_autenticacion
from backend.models.usuario import Usuario

usuarios_bp = Blueprint("usuarios", __name__)

@usuarios_bp.route("/register", methods=["POST"])
def register():
    """Ruta para registrar nuevos usuarios."""
    data = request.get_json() or {}
    nombre = data.get("nombre", "").strip()
    email = data.get("email", "").strip()
    contrasena = data.get("contrasena", "")
    
    # Si nombre está vacío, creamos uno a partir del correo
    if not nombre and email:
        nombre = email.split("@")[0]
        
    response, status_code = procesar_registro(nombre, email, contrasena)
    return jsonify(response), status_code

@usuarios_bp.route("/login", methods=["POST"])
def login():
    """Ruta para iniciar sesión."""
    data = request.get_json() or {}
    email = data.get("email", "").strip()
    contrasena = data.get("contrasena", "")
    
    response, status_code = procesar_login(email, contrasena)
    return jsonify(response), status_code

@usuarios_bp.route("/usuarios/<int:id_usuario>/medidas", methods=["PUT"])
@requiere_autenticacion
def actualizar_medidas(id_usuario):
    """Ruta para actualizar medidas corporales del avatar de un usuario."""

    # El token demuestra quién eres; no puedes editar la cuenta de otra
    # persona aunque conozcas o adivines su id_usuario.
    if g.id_usuario != id_usuario:
        return jsonify({
            "error": "No puedes modificar los datos de otro usuario."
        }), 403

    data = request.get_json() or {}
    altura = data.get("altura")
    ancho_hombros = data.get("ancho_hombros")
    pecho = data.get("pecho")
    cintura = data.get("cintura")
    cadera = data.get("cadera")
    
    if None in (altura, ancho_hombros, pecho, cintura, cadera):
        return jsonify({"error": "Todas las medidas corporales son obligatorias."}), 400
        
    exito = Usuario.actualizar_medidas(id_usuario, altura, ancho_hombros, pecho, cintura, cadera)
    if exito:
        return jsonify({"mensaje": "Medidas de avatar actualizadas correctamente en la base de datos."}), 200
    else:
        return jsonify({"error": "No se pudo actualizar el registro en la base de datos."}), 500
