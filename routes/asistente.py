from flask import Blueprint, jsonify, request
from backend.ia.asistente_virtual import conversar, analizar_imagen_javes, NOMBRE_ASISTENTE

asistente_bp = Blueprint("asistente", __name__)

MAX_IMAGEN_JAVES_BYTES = 10 * 1024 * 1024
FORMATOS_IMAGEN = {"image/jpeg", "image/png", "image/webp"}


def _respuesta_error_ia(exc):
    detalle = str(exc)
    print(f"Error en asistente virtual: {detalle}")
    upper = detalle.upper()
    if any(codigo in upper for codigo in ("RESOURCE_EXHAUSTED", "429")):
        return jsonify({
            "error": "JAVES alcanzó temporalmente el límite de solicitudes de IA. Espera un momento y vuelve a intentarlo."
        }), 429
    if any(codigo in upper for codigo in ("UNAVAILABLE", "DEADLINE_EXCEEDED", "TIMEOUT", "TIMED OUT", "503", "504")):
        return jsonify({
            "error": "JAVES está recibiendo muchas solicitudes o el servicio tarda en responder. Inténtalo de nuevo en un momento."
        }), 503
    if any(codigo in upper for codigo in ("NOT_FOUND", "MODEL NOT FOUND")):
        return jsonify({
            "error": "El modelo de JAVES no está disponible en este momento. El administrador debe revisar la configuración de modelos."
        }), 503
    return jsonify({
        "error": "JAVES no pudo procesar tu solicitud en este momento."
    }), 500


@asistente_bp.route("/ia/asistente", methods=["POST"])
def asistente_chat():
    data = request.get_json(silent=True) or {}
    mensaje = str(data.get("mensaje") or "").strip()

    if not mensaje:
        return jsonify({"error": "Escribe un mensaje para JAVES."}), 400

    if len(mensaje) > 1000:
        mensaje = mensaje[:1000]

    historial = data.get("historial") or []
    if not isinstance(historial, list):
        historial = []

    pagina_actual = data.get("pagina") or "index.html"

    try:
        resultado, error = conversar(mensaje, historial, pagina_actual)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({
            "status": "success",
            "asistente": NOMBRE_ASISTENTE,
            "resultado": resultado,
        }), 200
    except Exception as exc:
        return _respuesta_error_ia(exc)


@asistente_bp.route("/ia/asistente-imagen", methods=["POST"])
def asistente_imagen():
    archivo = request.files.get("imagen")
    if not archivo:
        return jsonify({"error": "Adjunta una foto para que JAVES pueda analizarla."}), 400

    mime = archivo.mimetype or ""
    if mime not in FORMATOS_IMAGEN:
        return jsonify({"error": "Formato no compatible. Usa JPG, PNG o WEBP."}), 400

    imagen_bytes = archivo.read(MAX_IMAGEN_JAVES_BYTES + 1)
    if not imagen_bytes:
        return jsonify({"error": "La imagen está vacía."}), 400
    if len(imagen_bytes) > MAX_IMAGEN_JAVES_BYTES:
        return jsonify({"error": "La imagen supera el límite de 10 MB."}), 413

    mensaje = str(request.form.get("mensaje") or "").strip()[:700]

    try:
        resultado, error = analizar_imagen_javes(imagen_bytes, mime, mensaje)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({
            "status": "success",
            "asistente": NOMBRE_ASISTENTE,
            "resultado": resultado,
        }), 200
    except Exception as exc:
        return _respuesta_error_ia(exc)
