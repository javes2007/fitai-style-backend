from flask import Blueprint, jsonify, request

from backend.integrations.clima import obtener_clima
from backend.integrations.google_search import search_fashion
from backend.utils import cache

externos_bp = Blueprint("externos", __name__)


# ============================================================
# CLIMA REAL (OpenWeatherMap)
# ============================================================

@externos_bp.route("/clima", methods=["GET"])
def clima_actual():
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    if not lat or not lon:
        return jsonify({"error": "Faltan las coordenadas (lat, lon)."}), 400

    try:
        lat = float(lat)
        lon = float(lon)
    except ValueError:
        return jsonify({"error": "Coordenadas inválidas."}), 400

    # El clima no cambia segundo a segundo: cacheamos 10 min por zona
    # (redondeando las coordenadas) para no gastar cuota de la API.
    clave_cache = cache.hacer_clave("clima", round(lat, 2), round(lon, 2))
    resultado_cacheado = cache.obtener(clave_cache)

    if resultado_cacheado is not None:
        return jsonify({"status": "success", "clima": resultado_cacheado, "cache": True}), 200

    resultado, error = obtener_clima(lat, lon)

    if error:
        return jsonify({"error": error}), 503

    cache.guardar(clave_cache, resultado, ttl_segundos=600)

    return jsonify({"status": "success", "clima": resultado}), 200


# ============================================================
# BÚSQUEDA DE INSPIRACIÓN DE MODA (Google Custom Search)
# ============================================================

@externos_bp.route("/buscar-estilo", methods=["GET"])
def buscar_estilo():
    consulta = request.args.get("q", "").strip()

    if not consulta:
        return jsonify({"error": "Escribe qué quieres buscar."}), 400

    genero = request.args.get("genero") or None
    estilo = request.args.get("estilo") or None
    color = request.args.get("color") or None

    clave_cache = cache.hacer_clave("buscar-estilo", consulta, genero, estilo, color)
    resultado_cacheado = cache.obtener(clave_cache)

    if resultado_cacheado is not None:
        respuesta = dict(resultado_cacheado)
        respuesta["cache"] = True
        return jsonify(respuesta), 200

    try:
        import asyncio
        resultado = asyncio.run(
            search_fashion(consulta, gender=genero, style=estilo, color=color, num=8)
        )

    except RuntimeError as error:
        # Falta GOOGLE_API_KEY / GOOGLE_CSE_ID en el .env
        return jsonify({"error": str(error)}), 503

    if not resultado.get("success"):
        return jsonify({"error": resultado.get("error", "No se pudo buscar en este momento.")}), 503

    cache.guardar(clave_cache, resultado, ttl_segundos=900)

    return jsonify(resultado), 200
