"""Descubrimiento de productos externos. No simula disponibilidad ni precios."""
import logging
from urllib.parse import quote_plus

import requests
from flask import Blueprint, jsonify, request

tienda_bp = Blueprint("tienda", __name__)
logger = logging.getLogger(__name__)

TIENDAS = {
    "amazon": {"nombre": "Amazon", "url": "https://www.amazon.com/s?k={q}", "tipo": "busqueda_externa"},
    "shein": {"nombre": "SHEIN", "url": "https://www.shein.com/pdsearch/{q}/", "tipo": "busqueda_externa"},
    "temu": {"nombre": "Temu", "url": "https://www.temu.com/search_result.html?search_key={q}", "tipo": "busqueda_externa"},
    "mercadolibre": {"nombre": "Mercado Libre", "url": "https://listado.mercadolibre.com.co/{q}", "tipo": "api"},
    "otras": {"nombre": "Otras tiendas", "url": "https://www.google.com/search?q={q}+ropa+comprar", "tipo": "busqueda_web"},
}


@tienda_bp.route("/tienda/externos", methods=["GET"])
def buscar_productos_externos():
    consulta = str(request.args.get("q", "")).strip()
    if not consulta:
        return jsonify({"error": "Escribe qué prenda o estilo buscas."}), 400
    if len(consulta) > 120:
        return jsonify({"error": "La búsqueda no puede superar 120 caracteres."}), 400

    encoded = quote_plus(consulta)
    enlaces = [
        {"id": key, "nombre": value["nombre"], "url": value["url"].format(q=encoded), "tipo": value["tipo"]}
        for key, value in TIENDAS.items()
    ]

    productos = []
    error_ml = None
    try:
        response = requests.get(
            "https://api.mercadolibre.com/sites/MCO/search",
            params={"q": consulta, "limit": 12},
            headers={"Accept": "application/json", "User-Agent": "FitAI-Style/1.0"},
            timeout=(4, 10),
        )
        if response.ok:
            payload = response.json()
            for item in payload.get("results", []):
                productos.append({
                    "id": str(item.get("id") or ""),
                    "titulo": str(item.get("title") or "Producto de Mercado Libre")[:250],
                    "precio": item.get("price"),
                    "moneda": item.get("currency_id") or "COP",
                    "imagen": item.get("thumbnail"),
                    "url": item.get("permalink"),
                    "vendedor": (item.get("seller") or {}).get("nickname"),
                    "fuente": "Mercado Libre",
                })
        else:
            error_ml = "Mercado Libre no está respondiendo ahora."
    except (requests.RequestException, ValueError):
        logger.warning("Búsqueda de Mercado Libre no disponible", exc_info=True)
        error_ml = "No se pudo consultar Mercado Libre en este momento."

    return jsonify({
        "consulta": consulta,
        "productos": productos,
        "tiendas": enlaces,
        "nota": "Los precios y la disponibilidad pertenecen a cada tienda y pueden cambiar. La compra de productos externos se completa en el sitio del vendedor.",
        "mercado_libre_error": error_ml,
    }), 200
