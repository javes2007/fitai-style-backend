"""
Servicio de autenticación de usuarios para FitAI.

Responsabilidades:
- Validar las credenciales recibidas.
- Normalizar el correo electrónico.
- Buscar el usuario en la base de datos.
- Verificar la contraseña mediante su hash.
- Devolver únicamente información pública del usuario.
- Manejar errores de base de datos.
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


def _normalizar_email(email):
    """Limpia y normaliza el correo electrónico."""
    return email.strip().lower()


def _validar_email(email):
    """Comprueba que el correo tenga un formato válido."""
    return bool(EMAIL_REGEX.match(email))


# ============================================================
# CONVERSIÓN DE DATOS
# ============================================================

def _convertir_medida(valor):
    """
    Convierte una medida almacenada en MySQL a float.

    Si el valor es NULL, vacío o inválido, devuelve None.
    """

    if valor is None:
        return None

    try:
        return float(valor)

    except (TypeError, ValueError):
        return None


# ============================================================
# DATOS PÚBLICOS DEL USUARIO
# ============================================================

def _datos_publicos(usuario):
    """
    Construye el objeto que se enviará al frontend.

    IMPORTANTE:
    Nunca se incluye la contraseña ni su hash.
    """

    return {
        "id_usuario": usuario.get("id_usuario"),
        "nombre": usuario.get("nombre"),
        "email": usuario.get("email"),

        # Características corporales
        "altura": _convertir_medida(
            usuario.get("altura")
        ),

        "ancho_hombros": _convertir_medida(
            usuario.get("ancho_hombros")
        ),

        "pecho": _convertir_medida(
            usuario.get("pecho")
        ),

        "cintura": _convertir_medida(
            usuario.get("cintura")
        ),

        "cadera": _convertir_medida(
            usuario.get("cadera")
        )
    }


# ============================================================
# LOGIN
# ============================================================

def procesar_login(email, contrasena):
    """
    Autentica un usuario de FitAI.

    Retorna:
        (respuesta, código_http)
    """

    # --------------------------------------------------------
    # 1. Comprobar campos obligatorios
    # --------------------------------------------------------

    if not email or not contrasena:
        return {
            "success": False,
            "error": "El correo y la contraseña son obligatorios."
        }, 400

    # --------------------------------------------------------
    # 2. Comprobar tipos
    # --------------------------------------------------------

    if not isinstance(email, str):
        return {
            "success": False,
            "error": "El correo electrónico no es válido."
        }, 400

    if not isinstance(contrasena, str):
        return {
            "success": False,
            "error": "La contraseña no es válida."
        }, 400

    # --------------------------------------------------------
    # 3. Normalizar correo
    # --------------------------------------------------------

    email = _normalizar_email(email)

    # --------------------------------------------------------
    # 4. Validar formato
    # --------------------------------------------------------

    if not _validar_email(email):
        return {
            "success": False,
            "error": "El correo electrónico no tiene un formato válido."
        }, 400

    # --------------------------------------------------------
    # 5. Buscar usuario
    # --------------------------------------------------------

    try:

        usuario = Usuario.obtener_por_email(email)

    except Exception:
        # No exponemos detalles internos de MySQL al cliente.
        return {
            "success": False,
            "error": "No se pudo procesar el inicio de sesión."
        }, 500

    # --------------------------------------------------------
    # 6. Usuario inexistente
    # --------------------------------------------------------

    if not usuario:
        return {
            "success": False,
            "error": "Correo o contraseña incorrectos."
        }, 401

    # --------------------------------------------------------
    # 7. Obtener contraseña almacenada
    # --------------------------------------------------------

    contrasena_hash = usuario.get("contrasena")

    if not contrasena_hash:
        return {
            "success": False,
            "error": "No se pudo validar la cuenta."
        }, 401

    # --------------------------------------------------------
    # 8. Verificar contraseña
    # --------------------------------------------------------

    try:

        contraseña_correcta = Usuario.verificar_contrasena(
            contrasena_hash,
            contrasena
        )

    except Exception:
        return {
            "success": False,
            "error": "No se pudo verificar la contraseña."
        }, 500

    # --------------------------------------------------------
    # 9. Contraseña incorrecta
    # --------------------------------------------------------

    if not contraseña_correcta:
        return {
            "success": False,
            "error": "Correo o contraseña incorrectos."
        }, 401

    # --------------------------------------------------------
    # 10. Login exitoso
    # --------------------------------------------------------

    datos_usuario = _datos_publicos(usuario)

    return {
        "success": True,

        "mensaje": "Inicio de sesión exitoso.",

        "usuario": datos_usuario,

        # Token de sesión: el frontend debe enviarlo como
        # "Authorization: Bearer <token>" en rutas protegidas.
        "token": generar_token(usuario["id_usuario"])
    }, 200
