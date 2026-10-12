"""Descubrimiento de productos externos. No simula disponibilidad ni precios."""
import logging
import os
import hmac
from decimal import Decimal, InvalidOperation
from urllib.parse import quote_plus

import requests
from flask import Blueprint, jsonify, request
from backend.database.conexion import obtener_conexion
from backend.routes.ropa import _asegurar_catalogo

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


def _asegurar_inventario(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS tienda_stock (
        id_prenda INT PRIMARY KEY,
        stock INT NOT NULL DEFAULT 0,
        activo TINYINT(1) NOT NULL DEFAULT 1,
        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_tienda_stock_activo (activo, stock)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cursor.execute("""INSERT IGNORE INTO tienda_stock (id_prenda, stock, activo)
                      SELECT id_prenda, 0, 1 FROM prendas WHERE id_usuario IS NULL""")


def _admin_autorizado():
    expected = os.environ.get("STORE_ADMIN_TOKEN", "").strip()
    provided = request.headers.get("X-Store-Admin-Token", "").strip()
    return bool(expected and provided and hmac.compare_digest(expected, provided))


def _validar_precio(value):
    try:
        price = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not price.is_finite() or price < Decimal("1000") or price > Decimal("20000000"):
        return None
    return price


@tienda_bp.route("/tienda/catalogo", methods=["GET"])
def catalogo_propio():
    try:
        limit = max(1, min(int(request.args.get("limite", 100)), 200))
    except (TypeError, ValueError):
        return jsonify({"error": "El límite debe estar entre 1 y 200."}), 400
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            _asegurar_catalogo(cursor)
            _asegurar_inventario(cursor)
            conn.commit()
            cursor.execute("""SELECT p.id_prenda,p.nombre_prenda,p.categoria,p.color,p.talla,p.estilo,
                                     p.temporada,p.url_imagen,p.precio,s.stock,s.activo
                              FROM prendas p JOIN tienda_stock s ON s.id_prenda=p.id_prenda
                              WHERE p.id_usuario IS NULL
                              ORDER BY p.id_prenda LIMIT %s""", (limit,))
            products = []
            for row in cursor.fetchall():
                price = _validar_precio(row.get("precio"))
                stock = int(row.get("stock") or 0)
                products.append({
                    "id": int(row["id_prenda"]),
                    "id_prenda": int(row["id_prenda"]),
                    "nombre": row["nombre_prenda"],
                    "nombre_prenda": row["nombre_prenda"],
                    "categoria": row.get("categoria"),
                    "color": row.get("color"),
                    "talla": row.get("talla"),
                    "estilo": row.get("estilo"),
                    "temporada": row.get("temporada"),
                    "url_imagen": row.get("url_imagen"),
                    "precio": float(row["precio"]) if row.get("precio") is not None else None,
                    "precio_valido": price is not None,
                    "stock": stock,
                    "activo": bool(row.get("activo")),
                    "disponible_para_compra": bool(row.get("activo")) and stock > 0 and price is not None,
                    "origen": "catalogo",
                })
            return jsonify(products), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo cargar el catálogo de la tienda."}), 503
    finally:
        conn.close()


@tienda_bp.route("/tienda/admin/productos", methods=["POST"])
def admin_crear_producto():
    if not os.environ.get("STORE_ADMIN_TOKEN", "").strip():
        return jsonify({"error": "Configura STORE_ADMIN_TOKEN en el backend."}), 503
    if not _admin_autorizado():
        return jsonify({"error": "No autorizado."}), 401
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400
    nombre = str(data.get("nombre", "")).strip()
    price = _validar_precio(data.get("precio"))
    try:
        stock = int(data.get("stock", 0))
        if stock < 0 or stock > 100000:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"error": "El stock debe estar entre 0 y 100000."}), 400
    if not nombre or len(nombre) > 100:
        return jsonify({"error": "El nombre es obligatorio (máximo 100 caracteres)."}), 400
    if price is None:
        return jsonify({"error": "El precio debe ser un valor real en COP entre 1.000 y 20.000.000."}), 400
    image = str(data.get("url_imagen", "")).strip()[:500] or None
    if image and not (image.startswith("https://") or image.startswith("img/") or image.startswith("/uploads/")):
        return jsonify({"error": "La imagen debe ser HTTPS o una ruta local de imagen."}), 400
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            _asegurar_inventario(cursor)
            cursor.execute("""INSERT INTO prendas
                (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s)""", (
                nombre, str(data.get("categoria", "Casual")).strip()[:50] or "Casual",
                str(data.get("color", "")).strip()[:50] or None,
                str(data.get("talla", "")).strip()[:20] or None,
                str(data.get("estilo", "casual")).strip()[:50] or "casual",
                str(data.get("temporada", "todo")).strip()[:30] or "todo", image, str(price),
            ))
            product_id = int(cursor.lastrowid)
            cursor.execute("""INSERT INTO tienda_stock (id_prenda,stock,activo)
                              VALUES (%s,%s,1)
                              ON DUPLICATE KEY UPDATE stock=VALUES(stock),activo=1""",
                           (product_id, stock))
        conn.commit()
        return jsonify({"success": True, "id_prenda": product_id, "stock": stock}), 201
    except Exception:
        conn.rollback()
        logger.exception("No se pudo crear producto de tienda")
        return jsonify({"error": "No se pudo crear el producto."}), 500
    finally:
        conn.close()


@tienda_bp.route("/tienda/admin/productos/<int:id_prenda>", methods=["PATCH"])
def admin_actualizar_producto(id_prenda):
    if not os.environ.get("STORE_ADMIN_TOKEN", "").strip():
        return jsonify({"error": "Configura STORE_ADMIN_TOKEN en el backend."}), 503
    if not _admin_autorizado():
        return jsonify({"error": "No autorizado."}), 401
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400
    if not any(key in data for key in ("precio", "stock", "activo")):
        return jsonify({"error": "Envía precio, stock o activo."}), 400
    price = _validar_precio(data["precio"]) if "precio" in data else None
    if "precio" in data and price is None:
        return jsonify({"error": "El precio debe ser un valor real en COP entre 1.000 y 20.000.000."}), 400
    stock = None
    if "stock" in data:
        try:
            stock = int(data["stock"])
            if stock < 0 or stock > 100000:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "El stock debe estar entre 0 y 100000."}), 400
    if "activo" in data and not isinstance(data["activo"], bool):
        return jsonify({"error": "activo debe ser true o false."}), 400
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            _asegurar_inventario(cursor)
            cursor.execute("SELECT id_prenda FROM prendas WHERE id_prenda=%s AND id_usuario IS NULL FOR UPDATE", (id_prenda,))
            if not cursor.fetchone():
                conn.rollback()
                return jsonify({"error": "Producto de catálogo no encontrado."}), 404
            if "precio" in data:
                cursor.execute("UPDATE prendas SET precio=%s WHERE id_prenda=%s AND id_usuario IS NULL", (str(price), id_prenda))
            fields, values = [], []
            if stock is not None:
                fields.append("stock=%s")
                values.append(stock)
            if "activo" in data:
                fields.append("activo=%s")
                values.append(1 if data["activo"] else 0)
            if fields:
                cursor.execute("UPDATE tienda_stock SET " + ", ".join(fields) + " WHERE id_prenda=%s", [*values, id_prenda])
        conn.commit()
        return jsonify({"success": True, "id_prenda": id_prenda, "mensaje": "Producto actualizado."}), 200
    except Exception:
        conn.rollback()
        logger.exception("No se pudo actualizar producto de tienda")
        return jsonify({"error": "No se pudo actualizar el producto."}), 500
    finally:
        conn.close()

