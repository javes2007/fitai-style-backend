"""
Tokens de sesión (JWT) para FitAI.

Por qué existe este archivo:
Antes, cualquiera podía llamar a PUT /usuarios/<id>/medidas con
cualquier id y sobrescribir los datos de otra persona, porque el
backend no tenía forma de saber quién hacía realmente la petición.

Ahora, al hacer login o registro, el backend entrega un token firmado
(JWT). El frontend debe enviarlo en la cabecera "Authorization: Bearer
<token>" en las rutas protegidas, y el backend verifica que el token
sea válido y que corresponda al usuario que se quiere modificar.

Nota honesta: si no defines SECRET_KEY en tu .env, se genera una clave
aleatoria distinta cada vez que arranca el servidor, así que los
tokens emitidos antes de reiniciar dejan de ser válidos (los usuarios
solo tendrían que volver a iniciar sesión). Para producción, define
SECRET_KEY en el .env para que no pase esto.
"""

import time
from functools import wraps

import jwt  # pyright: ignore[reportMissingImports]
from flask import request, jsonify, g

from backend.config import Config

ALGORITMO = "HS256"
EXPIRACION_SEGUNDOS = 30 * 24 * 60 * 60  # 30 días


def generar_token(id_usuario):
    """Crea un token de sesión firmado para un usuario ya autenticado."""
    ahora = int(time.time())
    payload = {
        "id_usuario": id_usuario,
        "iat": ahora,
        "exp": ahora + EXPIRACION_SEGUNDOS,
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm=ALGORITMO)


def verificar_token(token):
    """Decodifica un token. Devuelve el payload o None si no es válido/expiró."""
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=[ALGORITMO])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def requiere_autenticacion(vista):
    """
    Decorador para rutas que necesitan un usuario autenticado.

    Si el token es válido, deja el id del usuario en `g.id_usuario`
    para que la ruta lo use (por ejemplo, para comparar contra el id
    de la URL y evitar que alguien edite la cuenta de otra persona).
    """

    @wraps(vista)
    def envoltorio(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({
                "error": "Debes iniciar sesión para hacer esto."
            }), 401

        token = auth_header[len("Bearer "):].strip()
        payload = verificar_token(token)

        if not payload:
            return jsonify({
                "error": "Tu sesión no es válida o expiró. Inicia sesión de nuevo."
            }), 401

        g.id_usuario = payload.get("id_usuario")

        return vista(*args, **kwargs)

    return envoltorio
