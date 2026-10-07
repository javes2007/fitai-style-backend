"""
Servicio de registro de usuarios para FitAI.

Responsabilidades:
- Validar los datos recibidos.
- Normalizar nombre y correo.
- Verificar que el correo no esté registrado.
- Crear el usuario mediante el modelo Usuario.
- Manejar errores de base de datos inesperados.
- Devolver respuestas apropiadas para Flask/API.
"""

import re

from backend.models.usuario import Usuario
from backend.auth.tokens import generar_token


# ============================================================
# VALIDACIONES
# ============================================================

EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
)


def _validar_email(email):
    """Comprueba que el correo tenga un formato válido."""
    return bool(EMAIL_REGEX.match(email))


def _normalizar_nombre(nombre):
    """Limpia espacios innecesarios y normaliza el nombre."""
    return " ".join(nombre.strip().split())


def _normalizar_email(email):
    """Normaliza el correo para evitar duplicados por mayúsculas."""
    return email.strip().lower()


def _validar_contrasena(contrasena):
    """
    Valida los requisitos mínimos de seguridad de la contraseña.

    Se exige:
    - Mínimo 8 caracteres.
    - Al menos una letra.
    - Al menos un número.
    """
    if len(contrasena) < 8:
        return False

    if not re.search(r"[A-Za-z]", contrasena):
        return False

    if not re.search(r"\d", contrasena):
        return False

    return True


# ============================================================
# REGISTRO
# ============================================================

def procesar_registro(nombre, email, contrasena):
    """
    Procesa el registro de un nuevo usuario.

    Retorna:
        (respuesta, código_http)
    """

    # --------------------------------------------------------
    # 1. Comprobar campos obligatorios
    # --------------------------------------------------------

    if not nombre or not email or not contrasena:
        return {
            "success": False,
            "error": "Todos los campos son obligatorios."
        }, 400

    # --------------------------------------------------------
    # 2. Comprobar tipos
    # --------------------------------------------------------

    if not isinstance(nombre, str):
        return {
            "success": False,
            "error": "El nombre no es válido."
        }, 400

    if not isinstance(email, str):
        return {
            "success": False,
            "error": "El correo no es válido."
        }, 400

    if not isinstance(contrasena, str):
        return {
            "success": False,
            "error": "La contraseña no es válida."
        }, 400

    # --------------------------------------------------------
    # 3. Normalizar información
    # --------------------------------------------------------

    nombre = _normalizar_nombre(nombre)
    email = _normalizar_email(email)

    # --------------------------------------------------------
    # 4. Validar nombre
    # --------------------------------------------------------

    if len(nombre) < 2:
        return {
            "success": False,
            "error": "El nombre debe tener al menos 2 caracteres."
        }, 400

    if len(nombre) > 100:
        return {
            "success": False,
            "error": "El nombre es demasiado largo."
        }, 400

    # --------------------------------------------------------
    # 5. Validar correo
    # --------------------------------------------------------

    if not _validar_email(email):
        return {
            "success": False,
            "error": "El correo electrónico no tiene un formato válido."
        }, 400

    # --------------------------------------------------------
    # 6. Validar contraseña
    # --------------------------------------------------------

    if not _validar_contrasena(contrasena):
        return {
            "success": False,
            "error": (
                "La contraseña debe tener al menos 8 caracteres, "
                "una letra y un número."
            )
        }, 400

    # --------------------------------------------------------
    # 7. Comprobar usuario existente
    # --------------------------------------------------------

    try:

        usuario_existente = Usuario.obtener_por_email(email)

        if usuario_existente:
            return {
                "success": False,
                "error": "El correo ya está registrado."
            }, 409

    except Exception:
        return {
            "success": False,
            "error": "No se pudo verificar el correo en la base de datos."
        }, 500

    # --------------------------------------------------------
    # 8. Crear usuario
    # --------------------------------------------------------

    try:

        id_usuario = Usuario.crear(
            nombre,
            email,
            contrasena
        )

    except Exception:
        return {
            "success": False,
            "error": "Ocurrió un error al registrar el usuario."
        }, 500

    # --------------------------------------------------------
    # 9. Comprobar resultado
    # --------------------------------------------------------

    if not id_usuario:
        return {
            "success": False,
            "error": "No se pudo completar el registro."
        }, 500

    # --------------------------------------------------------
    # 10. Respuesta exitosa
    # --------------------------------------------------------

    return {
        "success": True,
        "mensaje": "Usuario registrado exitosamente.",
        "usuario": {
            "id_usuario": id_usuario,
            "nombre": nombre,
            "email": email
        }
    }, 201
