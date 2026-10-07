from flask import Blueprint, jsonify, request
from backend.ia.asistente_virtual import conversar, NOMBRE_ASISTENTE

asistente_bp = Blueprint("asistente", __name__)


@asistente_bp.route("/ia/asistente", methods=["POST"])
def asistente_chat():
    data = request.get_json(silent=True) or {}

    mensaje = (data.get("mensaje") or "").strip()
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
        print(f"Error en asistente virtual: {exc}")
        return jsonify({
            "error": "JAVES no pudo procesar tu mensaje en este momento."
        }), 500
