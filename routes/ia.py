from flask import Blueprint, jsonify, request  # pyright: ignore[reportMissingImports]
from backend.ia.consultor_imagen import consultar_imagen
from backend.ia.mediapipe_ai import analizar_medidas
from backend.utils import cache

import os
import uuid
import cv2
import numpy as np


ia_bp = Blueprint("ia", __name__)


MAX_IMAGE_BYTES = 16 * 1024 * 1024

def _leer_imagen_segura(archivo):
    data = archivo.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("La imagen supera el límite de 16 MB.")
    if not data:
        raise ValueError("La imagen está vacía.")
    imagen = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if imagen is None:
        raise ValueError("El archivo no contiene una imagen válida.")
    return data


# ============================================================
# CONSULTOR DE IMAGEN
# ============================================================

@ia_bp.route("/ia/consultor-imagen", methods=["POST"])
def consultor_imagen():

    archivo = request.files.get("imagen")

    if not archivo:
        return jsonify({
            "error": "Sube una imagen para que FitAI pueda analizarla."
        }), 400

    mime = archivo.mimetype or "image/jpeg"

    if mime not in {
        "image/jpeg",
        "image/png",
        "image/webp"
    }:
        return jsonify({
            "error": "Formato no compatible. Usa JPG, PNG o WEBP."
        }), 400

    contexto = {
        "ocasion": request.form.get(
            "ocasion",
            "diario"
        ),

        "estilo": request.form.get(
            "estilo",
            "casual"
        ),

        "clima": request.form.get(
            "clima",
            "cálido"
        ),

        "presupuesto": request.form.get(
            "presupuesto",
            "medio"
        ),
    }

    try:
        imagen_bytes = _leer_imagen_segura(archivo)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Si ya analizamos exactamente esta imagen con este mismo contexto
    # recientemente, devolvemos el resultado guardado en vez de volver a
    # llamar a la IA (ahorra costo y tiempo en subidas repetidas/dobles).
    clave_cache = cache.hacer_clave(
        "consultor-imagen", imagen_bytes, contexto
    )

    resultado_cacheado = cache.obtener(clave_cache)

    if resultado_cacheado is not None:
        return jsonify({
            "status": "success",
            "resultado": resultado_cacheado,
            "cache": True
        }), 200

    try:

        resultado, error = consultar_imagen(
            imagen_bytes,
            mime,
            contexto
        )

        if error:
            return jsonify({
                "error": error
            }), 503

        cache.guardar(clave_cache, resultado, ttl_segundos=600)

        return jsonify({
            "status": "success",
            "resultado": resultado
        }), 200

    except Exception as exc:

        print(
            f"Error en consultor de imagen: {exc}"
        )

        texto_error = str(exc)

        # Google devuelve 503/"UNAVAILABLE" o 429/"RESOURCE_EXHAUSTED"
        # cuando el modelo está saturado o se llegó al límite gratis
        # por minuto — es temporal, no un problema de configuración.
        if "UNAVAILABLE" in texto_error or "503" in texto_error:
            return jsonify({
                "error": (
                    "El servicio de IA de Google está saturado en este "
                    "momento (pasa seguido con la capa gratuita). "
                    "Espera un minuto y vuelve a intentar."
                )
            }), 503

        if "RESOURCE_EXHAUSTED" in texto_error or "429" in texto_error:
            return jsonify({
                "error": (
                    "Se alcanzó el límite de uso gratuito de Gemini por "
                    "ahora. Espera un poco antes de volver a intentar."
                )
            }), 429

        return jsonify({
            "error": (
                "La IA no pudo analizar la imagen en este momento. "
                f"Detalle técnico: {texto_error[:200]}"
            )
        }), 500


# ============================================================
# ANÁLISIS CORPORAL CON MEDIAPIPE
# ============================================================

@ia_bp.route(
    "/ia/analizar-medidas",
    methods=["POST"]
)
def analizar_medidas_endpoint():

    archivo = request.files.get(
        "imagen"
    )

    if not archivo:

        return jsonify({
            "status": "error",
            "error": (
                "Debes subir una imagen "
                "para analizar el cuerpo."
            )
        }), 400


    # --------------------------------------------------------
    # VALIDAR FORMATO
    # --------------------------------------------------------

    mime = archivo.mimetype or ""

    formatos_permitidos = {
        "image/jpeg",
        "image/png",
        "image/webp"
    }

    if mime not in formatos_permitidos:

        return jsonify({
            "status": "error",
            "error": (
                "Formato no compatible. "
                "Usa JPG, PNG o WEBP."
            )
        }), 400


    # --------------------------------------------------------
    # ALTURA
    # --------------------------------------------------------

    try:

        altura = float(
            request.form.get(
                "altura",
                "170"
            )
        )

    except ValueError:

        return jsonify({
            "status": "error",
            "error": (
                "La altura debe ser "
                "un número."
            )
        }), 400


    if altura < 100 or altura > 250:

        return jsonify({
            "status": "error",
            "error": (
                "La altura debe estar "
                "entre 100 y 250 cm."
            )
        }), 400

    try:
        imagen_bytes = _leer_imagen_segura(archivo)
    except ValueError as exc:
        return jsonify({"status":"error", "error": str(exc)}), 400

    # Misma foto + misma altura ya analizada recientemente: evitamos
    # volver a ejecutar MediaPipe (es una operación pesada de CPU).
    clave_cache = cache.hacer_clave(
        "analizar-medidas", imagen_bytes, altura
    )

    resultado_cacheado = cache.obtener(clave_cache)

    if resultado_cacheado is not None:
        respuesta_cache = dict(resultado_cacheado)
        respuesta_cache["cache"] = True
        return jsonify(respuesta_cache), 200

    # --------------------------------------------------------
    # CREAR CARPETA TEMPORAL
    # --------------------------------------------------------

    carpeta = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        ),
        "temp"
    )

    os.makedirs(
        carpeta,
        exist_ok=True
    )


    # --------------------------------------------------------
    # CREAR NOMBRE ÚNICO
    # --------------------------------------------------------

    extension = ".jpg"

    if mime == "image/png":
        extension = ".png"

    elif mime == "image/webp":
        extension = ".webp"


    nombre = (
        f"{uuid.uuid4().hex}"
        f"{extension}"
    )

    ruta = os.path.join(
        carpeta,
        nombre
    )


    try:

        # ----------------------------------------------------
        # GUARDAR IMAGEN (temporal, se borra abajo)
        # ----------------------------------------------------

        with open(ruta, "wb") as f:
            f.write(imagen_bytes)


        # ----------------------------------------------------
        # MEDIA PIPE
        # ----------------------------------------------------

        resultado = analizar_medidas(
            ruta,
            altura
        )


        # ----------------------------------------------------
        # ELIMINAR IMAGEN TEMPORAL
        # ----------------------------------------------------

        try:
            os.remove(ruta)
        except OSError:
            pass


        # ----------------------------------------------------
        # CUERPO NO DETECTADO
        # ----------------------------------------------------

        if not resultado.get(
            "detectado",
            False
        ):

            return jsonify({
                "status": "error",
                "error": resultado.get(
                    "mensaje",
                    "No se pudo detectar el cuerpo."
                )
            }), 422


        # ----------------------------------------------------
        # RESPUESTA
        # ----------------------------------------------------

        respuesta_ok = {

            "status": "success",

            "mensaje": (
                "Análisis corporal "
                "realizado correctamente."
            ),

            "datos": resultado

        }

        cache.guardar(clave_cache, respuesta_ok, ttl_segundos=600)

        return jsonify(respuesta_ok), 200


    except Exception as exc:

        print(
            "ERROR EN MEDIAPIPE:",
            exc
        )


        # Intentar limpiar archivo
        try:

            if os.path.exists(ruta):
                os.remove(ruta)

        except OSError:
            pass


        return jsonify({

            "status": "error",

            "error": (
                "Ocurrió un error "
                "analizando la imagen."
            )

        }), 500