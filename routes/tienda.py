"""Tienda FitAI: catálogo propio, marketplaces y creación de checkout.

Las credenciales de pago se leen únicamente del entorno del servidor.
Los productos externos se compran directamente en el marketplace de origen.
"""
import hashlib
import os
import uuid
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

import requests
from flask import Blueprint, jsonify, request, g
from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion

tienda_bp = Blueprint("tienda", __name__)
PROVEEDORES_PAGO = {"mercadopago", "wompi"}
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://fitai-style-frontend.vercel.app").rstrip("/")
MARKETPLACES = {
    "amazon": {"nombre": "Amazon", "url": "https://www.amazon.com/"},
    "shein": {"nombre": "SHEIN", "url": "https://www.shein.com/"},
    "temu": {"nombre": "Temu", "url": "https://www.temu.com/"},
    "mercadolibre": {"nombre": "Mercado Libre", "url": "https://www.mercadolibre.com.co/"},
}


def _asegurar_tablas(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS tienda_pedidos (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        referencia VARCHAR(64) NOT NULL UNIQUE,
        id_usuario INT NOT NULL,
        proveedor_pago VARCHAR(20) NOT NULL,
        estado VARCHAR(30) NOT NULL DEFAULT 'pendiente_pago',
        total DECIMAL(12,2) NOT NULL,
        moneda CHAR(3) NOT NULL DEFAULT 'COP',
        checkout_url TEXT NULL,
        provider_order_id VARCHAR(120) NULL,
        datos_envio JSON NULL,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_tienda_usuario (id_usuario, creado_en),
        INDEX idx_tienda_estado (estado)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS tienda_pedido_detalles (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        id_pedido BIGINT NOT NULL,
        id_prenda INT NOT NULL,
        nombre VARCHAR(150) NOT NULL,
        precio_unitario DECIMAL(12,2) NOT NULL,
        cantidad INT NOT NULL,
        INDEX idx_tienda_detalles_pedido (id_pedido)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def _error(mensaje, codigo):
    return jsonify({"success": False, "error": mensaje}), codigo


def _money(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Precio inválido.")
    if not amount.is_finite() or amount <= 0 or amount > Decimal("10000000"):
        raise ValueError("El precio del producto no es válido.")
    return amount


def _buscar_mercado_libre(query, limit=8):
    if not query:
        return []
    try:
        response = requests.get(
            "https://api.mercadolibre.com/sites/MCO/search",
            params={"q": query[:120], "limit": max(1, min(limit, 20))},
            timeout=(3.05, 8),
            headers={"Accept": "application/json", "User-Agent": "FitAI-Style/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        items = []
        for item in payload.get("results", []):
            price = item.get("price")
            permalink = item.get("permalink")
            if not permalink or not str(permalink).startswith("https://"):
                continue
            try:
                price = float(price)
            except (TypeError, ValueError):
                price = None
            items.append({
                "id": "ml-" + str(item.get("id", "")),
                "nombre": str(item.get("title") or "Producto de Mercado Libre")[:180],
                "precio": price,
                "moneda": item.get("currency_id") or "COP",
                "url_imagen": item.get("thumbnail"),
                "url_compra": permalink,
                "proveedor": "mercadolibre",
                "tipo": "externo",
                "origen": "Mercado Libre",
            })
        return items
    except (requests.RequestException, ValueError, TypeError):
        # Una caída del proveedor no debe tumbar el catálogo propio.
        return []


@tienda_bp.route("/tienda/marketplaces", methods=["GET"])
def marketplaces():
    return jsonify({
        "marketplaces": [
            {"id": key, "nombre": value["nombre"], "url": value["url"], "tipo": "salida_externa"}
            for key, value in MARKETPLACES.items()
        ],
        "nota": "Los pagos de estas tiendas se completan en sus sitios oficiales. Los resultados de catálogo de terceros requieren acceso/API o afiliación aprobada."
    }), 200


@tienda_bp.route("/tienda/productos", methods=["GET"])
def productos_tienda():
    query = request.args.get("q", "").strip()[:120]
    origen = request.args.get("origen", "todos").strip().lower()
    try:
        limit = max(1, min(int(request.args.get("limite", 24)), 60))
    except (TypeError, ValueError):
        return _error("El límite debe ser un número entre 1 y 60.", 400)
    if origen not in {"todos", "propios", "mercadolibre"}:
        return _error("Origen no válido.", 400)

    productos = []
    if origen in {"todos", "propios"}:
        conn = obtener_conexion()
        if not conn:
            return _error("La base de datos no está disponible.", 503)
        try:
            with conn.cursor() as cursor:
                cursor.execute("""SELECT id_prenda, nombre_prenda, categoria, color, talla,
                                         estilo, url_imagen, precio
                                  FROM prendas
                                  WHERE id_usuario IS NULL AND precio > 0
                                  ORDER BY id_prenda DESC LIMIT %s""", (limit,))
                for row in cursor.fetchall():
                    if query and query.casefold() not in (
                        str(row.get("nombre_prenda") or "") + " " +
                        str(row.get("categoria") or "") + " " +
                        str(row.get("color") or "")
                    ).casefold():
                        continue
                    productos.append({
                        "id": int(row["id_prenda"]),
                        "id_prenda": int(row["id_prenda"]),
                        "nombre": row["nombre_prenda"],
                        "categoria": row.get("categoria"),
                        "color": row.get("color"),
                        "talla": row.get("talla"),
                        "estilo": row.get("estilo"),
                        "precio": float(row["precio"]),
                        "moneda": "COP",
                        "url_imagen": row.get("url_imagen"),
                        "proveedor": "fitai",
                        "tipo": "propio",
                        "origen": "FitAI Style",
                        "comprable_en_fitai": True,
                    })
        except Exception:
            return _error("No se pudo cargar el catálogo propio.", 503)
        finally:
            conn.close()

    externos = _buscar_mercado_libre(query, min(limit, 12)) if query and origen in {"todos", "mercadolibre"} else []
    productos.extend(externos)
    return jsonify({
        "success": True,
        "productos": productos,
        "total": len(productos),
        "fuentes": {"fitai": origen in {"todos", "propios"}, "mercadolibre": bool(externos)},
        "mensaje": "Los productos externos se compran en el sitio del vendedor."
    }), 200


@tienda_bp.route("/tienda/checkout", methods=["POST"])
@requiere_autenticacion
def crear_checkout():
    data = request.get_json(silent=True) or {}
    proveedor = str(data.get("proveedor_pago", "")).strip().lower()
    items = data.get("items")
    envio = data.get("envio") or {}
    if proveedor not in PROVEEDORES_PAGO:
        return _error("Selecciona Mercado Pago o Wompi.", 400)
    if not isinstance(items, list) or not items or len(items) > 30:
        return _error("El carrito debe contener entre 1 y 30 productos.", 400)

    # Datos mínimos para preparar un pedido físico; nunca se confía en el precio del navegador.
    campos_envio = ("nombre", "telefono", "direccion", "ciudad", "departamento", "email")
    envio_limpio = {k: str(envio.get(k, "")).strip()[:180] for k in campos_envio}
    if any(not envio_limpio[k] for k in campos_envio):
        return _error("Completa nombre, correo, teléfono, dirección, ciudad y departamento para el envío.", 400)
    if "@" not in envio_limpio["email"] or len(envio_limpio["email"]) > 180:
        return _error("El correo de envío no es válido.", 400)

    cantidades = {}
    try:
        for item in items:
            if not isinstance(item, dict):
                raise ValueError
            product_id = int(item.get("id_prenda", item.get("id")))
            quantity = int(item.get("cantidad", 1))
            if product_id <= 0 or quantity < 1 or quantity > 10:
                raise ValueError
            cantidades[product_id] = min(10, cantidades.get(product_id, 0) + quantity)
            if cantidades[product_id] > 10:
                raise ValueError
    except (TypeError, ValueError):
        return _error("Hay productos o cantidades no válidos en el carrito.", 400)

    conn = obtener_conexion()
    if not conn:
        return _error("La base de datos no está disponible.", 503)
    reference = "FITAI-" + uuid.uuid4().hex.upper()
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            ids = list(cantidades)
            placeholders = ",".join(["%s"] * len(ids))
            cursor.execute(
                f"""SELECT id_prenda, nombre_prenda, precio, url_imagen
                    FROM prendas WHERE id_usuario IS NULL AND id_prenda IN ({placeholders})""",
                ids,
            )
            rows = {int(row["id_prenda"]): row for row in cursor.fetchall()}
            if len(rows) != len(ids):
                conn.rollback()
                return _error("Uno o más productos ya no están disponibles en la tienda propia.", 409)
            line_items = []
            total = Decimal("0.00")
            for product_id, quantity in cantidades.items():
                row = rows[product_id]
                price = _money(row.get("precio"))
                total += price * quantity
                line_items.append({
                    "id": product_id,
                    "nombre": str(row["nombre_prenda"])[:150],
                    "precio": price,
                    "cantidad": quantity,
                })
            total = total.quantize(Decimal("0.01"))
            if total <= 0 or total > Decimal("10000000"):
                conn.rollback()
                return _error("El total del pedido está fuera del rango permitido.", 400)

            cursor.execute(
                """INSERT INTO tienda_pedidos
                   (referencia,id_usuario,proveedor_pago,estado,total,moneda,datos_envio)
                   VALUES (%s,%s,%s,'preparando_pago',%s,'COP',%s)""",
                (reference, g.id_usuario, proveedor, str(total), __import__("json").dumps(envio_limpio, ensure_ascii=False)),
            )
            order_id = cursor.lastrowid
            for line in line_items:
                cursor.execute(
                    """INSERT INTO tienda_pedido_detalles
                       (id_pedido,id_prenda,nombre,precio_unitario,cantidad)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (order_id, line["id"], line["nombre"], str(line["precio"]), line["cantidad"]),
                )
        conn.commit()

        checkout_url = None
        provider_order_id = None
        if proveedor == "mercadopago":
            token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
            if not token:
                _marcar_error(reference)
                return _error("Mercado Pago aún no está configurado en el servidor (falta MP_ACCESS_TOKEN).", 503)
            body = {
                "items": [{
                    "id": str(line["id"]),
                    "title": line["nombre"],
                    "quantity": line["cantidad"],
                    "unit_price": float(line["precio"]),
                    "currency_id": "COP",
                } for line in line_items],
                "external_reference": reference,
                "notification_url": os.environ.get("MP_NOTIFICATION_URL") or None,
                "back_urls": {
                    "success": FRONTEND_URL + "/ropa.html?pedido=" + reference + "&resultado=exito",
                    "failure": FRONTEND_URL + "/ropa.html?pedido=" + reference + "&resultado=fallo",
                    "pending": FRONTEND_URL + "/ropa.html?pedido=" + reference + "&resultado=pendiente",
                },
                "auto_return": "approved",
                "statement_descriptor": "FITAI STYLE",
            }
            body = {key: value for key, value in body.items() if value is not None}
            try:
                response = requests.post(
                    "https://api.mercadopago.com/checkout/preferences",
                    json=body,
                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
                    timeout=(3.05, 12),
                )
                response.raise_for_status()
                result = response.json()
                checkout_url = result.get("init_point")
                provider_order_id = str(result.get("id") or "")
                if not checkout_url or not checkout_url.startswith("https://"):
                    raise ValueError("La pasarela no devolvió un enlace de pago válido.")
            except (requests.RequestException, ValueError, TypeError):
                _marcar_error(reference)
                return _error("Mercado Pago no pudo preparar el checkout. El pedido no se ha cobrado.", 502)
        else:
            public_key = os.environ.get("WOMPI_PUBLIC_KEY", "").strip()
            integrity_secret = os.environ.get("WOMPI_INTEGRITY_SECRET", "").strip()
            if not public_key or not integrity_secret:
                _marcar_error(reference)
                return _error("Wompi aún no está configurado en el servidor (faltan WOMPI_PUBLIC_KEY y WOMPI_INTEGRITY_SECRET).", 503)
            amount_cents = int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            signature = hashlib.sha256(
                f"{reference}{amount_cents}COP{integrity_secret}".encode("utf-8")
            ).hexdigest()
            params = {
                "public-key": public_key,
                "currency": "COP",
                "amount-in-cents": amount_cents,
                "reference": reference,
                "signature:integrity": signature,
                "redirect-url": FRONTEND_URL + "/ropa.html?pedido=" + reference + "&resultado=retorno",
            }
            checkout_url = "https://checkout.wompi.co/p/?" + urlencode(params)

        with conn.cursor() as cursor:
            cursor.execute(
                """UPDATE tienda_pedidos SET estado='pendiente_pago',checkout_url=%s,
                   provider_order_id=%s WHERE referencia=%s AND id_usuario=%s""",
                (checkout_url, provider_order_id, reference, g.id_usuario),
            )
        conn.commit()
        return jsonify({
            "success": True,
            "referencia": reference,
            "estado": "pendiente_pago",
            "total": float(total),
            "moneda": "COP",
            "proveedor_pago": proveedor,
            "checkout_url": checkout_url,
            "mensaje": "Pedido creado. El pago aún no está confirmado; se debe verificar con la pasarela."
        }), 201
    except Exception:
        conn.rollback()
        return _error("No se pudo preparar el pedido. No se ha confirmado ningún cobro.", 500)
    finally:
        conn.close()


def _marcar_error(reference):
    conn = obtener_conexion()
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute(
                "UPDATE tienda_pedidos SET estado='error_checkout' WHERE referencia=%s",
                (reference,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


@tienda_bp.route("/tienda/pedidos", methods=["GET"])
@requiere_autenticacion
def pedidos_usuario():
    conn = obtener_conexion()
    if not conn:
        return _error("La base de datos no está disponible.", 503)
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute(
                """SELECT referencia,proveedor_pago,estado,total,moneda,checkout_url,creado_en
                   FROM tienda_pedidos WHERE id_usuario=%s ORDER BY creado_en DESC LIMIT 50""",
                (g.id_usuario,),
            )
            rows = cursor.fetchall()
            for row in rows:
                row["total"] = float(row["total"])
                if row.get("creado_en"):
                    row["creado_en"] = row["creado_en"].isoformat()
            return jsonify({"success": True, "pedidos": rows}), 200
    finally:
        conn.close()
