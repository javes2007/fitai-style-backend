"""Tienda FitAI: catálogo propio, marketplaces y creación de checkout.

Las credenciales de pago se leen únicamente del entorno del servidor.
Los productos externos se compran directamente en el marketplace de origen.
"""
import hashlib
import json
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
    cursor.execute("""CREATE TABLE IF NOT EXISTS tienda_productos (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        nombre VARCHAR(180) NOT NULL,
        descripcion VARCHAR(1000) NULL,
        categoria VARCHAR(80) NULL,
        color VARCHAR(80) NULL,
        talla VARCHAR(40) NULL,
        precio DECIMAL(12,2) NOT NULL,
        moneda CHAR(3) NOT NULL DEFAULT 'COP',
        url_imagen VARCHAR(700) NULL,
        stock INT NOT NULL DEFAULT 0,
        activo TINYINT(1) NOT NULL DEFAULT 1,
        creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_tienda_producto_activo (activo, stock),
        INDEX idx_tienda_producto_categoria (categoria)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
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
        id_producto BIGINT NOT NULL,
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
                _asegurar_tablas(cursor)
                conn.commit()
                cursor.execute("""SELECT id,nombre,descripcion,categoria,color,talla,precio,moneda,url_imagen,stock
                                  FROM tienda_productos WHERE activo=1 AND stock > 0
                                  ORDER BY creado_en DESC LIMIT %s""", (limit,))
                for row in cursor.fetchall():
                    searchable = " ".join(str(row.get(k) or "") for k in ("nombre", "descripcion", "categoria", "color"))
                    if query and not any(token.casefold() in searchable.casefold() for token in query.split()):
                        continue
                    productos.append({
                        "id": int(row["id"]), "id_producto": int(row["id"]), "id_prenda": int(row["id"]),
                        "nombre": row["nombre"], "descripcion": row.get("descripcion"),
                        "categoria": row.get("categoria"), "color": row.get("color"), "talla": row.get("talla"),
                        "precio": float(row["precio"]), "moneda": row.get("moneda") or "COP",
                        "url_imagen": row.get("url_imagen"), "stock": int(row.get("stock") or 0),
                        "proveedor": "fitai", "tipo": "propio", "origen": "FitAI Style",
                        "comprable_en_fitai": True,
                    })
        except Exception:
            return _error("No se pudo cargar el catálogo propio.", 503)
        finally:
            conn.close()

    externos = _buscar_mercado_libre(query or "ropa", min(limit, 12)) if origen in {"todos", "mercadolibre"} else []
    productos.extend(externos)
    return jsonify({
        "success": True, "productos": productos, "total": len(productos),
        "fuentes": {"fitai": origen in {"todos", "propios"}, "mercadolibre": bool(externos)},
        "mensaje": "Los productos externos se compran en el sitio del vendedor."
    }), 200


@tienda_bp.route("/tienda/admin/productos", methods=["POST"])
def crear_producto_tienda():
    admin_token = os.environ.get("STORE_ADMIN_TOKEN", "").strip()
    supplied_token = request.headers.get("X-Store-Admin-Token", "").strip()
    if not admin_token:
        return _error("El administrador de la tienda aún no está configurado en el servidor.", 503)
    import hmac
    if not supplied_token or not hmac.compare_digest(supplied_token, admin_token):
        return _error("No autorizado para administrar productos.", 401)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _error("El cuerpo debe ser un objeto JSON.", 400)
    nombre = str(data.get("nombre", "")).strip()
    if not nombre or len(nombre) > 180:
        return _error("El nombre del producto es obligatorio (máximo 180 caracteres).", 400)
    try:
        precio = _money(data.get("precio"))
        stock = int(data.get("stock", 0))
        if stock < 0 or stock > 100000:
            raise ValueError
    except (ValueError, TypeError):
        return _error("El precio debe ser mayor que cero y el inventario entre 0 y 100000.", 400)
    image = str(data.get("url_imagen", "")).strip()[:700] or None
    if image and not (image.startswith("https://") or image.startswith("img/")):
        return _error("La imagen debe ser una URL HTTPS o una ruta local dentro de img/.", 400)
    conn = obtener_conexion()
    if not conn:
        return _error("La base de datos no está disponible.", 503)
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute("""INSERT INTO tienda_productos
                (nombre,descripcion,categoria,color,talla,precio,moneda,url_imagen,stock,activo)
                VALUES (%s,%s,%s,%s,%s,%s,'COP',%s,%s,1)""", (
                nombre, str(data.get("descripcion", "")).strip()[:1000] or None,
                str(data.get("categoria", "")).strip()[:80] or None,
                str(data.get("color", "")).strip()[:80] or None,
                str(data.get("talla", "")).strip()[:40] or None,
                str(precio), image, stock,
            ))
            product_id = cursor.lastrowid
        conn.commit()
        return jsonify({"success": True, "id_producto": product_id, "mensaje": "Producto creado en el catálogo propio."}), 201
    except Exception:
        conn.rollback()
        return _error("No se pudo crear el producto.", 500)
    finally:
        conn.close()


@tienda_bp.route("/tienda/admin/productos/<int:product_id>", methods=["PATCH"])
def actualizar_producto_tienda(product_id):
    admin_token = os.environ.get("STORE_ADMIN_TOKEN", "").strip()
    supplied_token = request.headers.get("X-Store-Admin-Token", "").strip()
    if not admin_token:
        return _error("El administrador de la tienda aún no está configurado en el servidor.", 503)
    import hmac
    if not supplied_token or not hmac.compare_digest(supplied_token, admin_token):
        return _error("No autorizado para administrar productos.", 401)
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _error("El cuerpo debe ser un objeto JSON.", 400)
    changes, values = [], []
    if "precio" in data:
        try:
            price = _money(data["precio"])
        except ValueError:
            return _error("El precio debe ser mayor que cero.", 400)
        changes.append("precio=%s")
        values.append(str(price))
    if "stock" in data:
        try:
            stock = int(data["stock"])
            if stock < 0 or stock > 100000:
                raise ValueError
        except (TypeError, ValueError):
            return _error("El inventario debe estar entre 0 y 100000.", 400)
        changes.append("stock=%s")
        values.append(stock)
    if "activo" in data:
        if not isinstance(data["activo"], bool):
            return _error("activo debe ser true o false.", 400)
        changes.append("activo=%s")
        values.append(1 if data["activo"] else 0)
    if not changes:
        return _error("Envía precio, stock o activo para actualizar.", 400)
    conn = obtener_conexion()
    if not conn:
        return _error("La base de datos no está disponible.", 503)
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute(
                "UPDATE tienda_productos SET " + ", ".join(changes) + " WHERE id=%s",
                [*values, product_id],
            )
            if cursor.rowcount == 0:
                conn.rollback()
                return _error("Producto no encontrado o sin cambios.", 404)
        conn.commit()
        return jsonify({"success": True, "id_producto": product_id, "mensaje": "Producto actualizado."}), 200
    except Exception:
        conn.rollback()
        return _error("No se pudo actualizar el producto.", 500)
    finally:
        conn.close()


@tienda_bp.route("/tienda/checkout", methods=["POST"])
@requiere_autenticacion
def crear_checkout():
    data = request.get_json(silent=True) or {}
    proveedor = str(data.get("proveedor_pago", "")).strip().lower()
    items = data.get("items")
    envio = data.get("envio") or {}
    if not isinstance(envio, dict):
        return _error("Los datos de envío no tienen un formato válido.", 400)
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
                f"""SELECT id, nombre, precio, stock
                    FROM tienda_productos WHERE activo=1 AND id IN ({placeholders}) FOR UPDATE""",
                ids,
            )
            rows = {int(row["id"]): row for row in cursor.fetchall()}
            if len(rows) != len(ids):
                conn.rollback()
                return _error("Uno o más productos ya no están disponibles en la tienda propia.", 409)
            line_items = []
            total = Decimal("0.00")
            for product_id, quantity in cantidades.items():
                row = rows[product_id]
                if int(row.get("stock") or 0) < quantity:
                    conn.rollback()
                    return _error("No hay inventario suficiente para uno de los productos.", 409)
                price = _money(row.get("precio"))
                total += price * quantity
                line_items.append({
                    "id": product_id,
                    "nombre": str(row["nombre"])[:150],
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
                (reference, g.id_usuario, proveedor, str(total), json.dumps(envio_limpio, ensure_ascii=False)),
            )
            order_id = cursor.lastrowid
            for line in line_items:
                cursor.execute(
                    """INSERT INTO tienda_pedido_detalles
                       (id_pedido,id_producto,nombre,precio_unitario,cantidad)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (order_id, line["id"], line["nombre"], str(line["precio"]), line["cantidad"]),
                )
                cursor.execute(
                    "UPDATE tienda_productos SET stock=stock-%s WHERE id=%s AND activo=1 AND stock >= %s",
                    (line["cantidad"], line["id"], line["cantidad"]),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Inventario insuficiente.")
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
                payments_env = os.environ.get("PAYMENTS_ENV", "sandbox").strip().lower()
                checkout_url = result.get("init_point") if payments_env == "production" else result.get("sandbox_init_point")
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
        _marcar_error(reference)
        return _error("No se pudo preparar el pedido. No se ha confirmado ningún cobro.", 500)
    finally:
        conn.close()


def _cambiar_estado_pedido(conn, reference, new_state, id_usuario=None):
    """Actualiza el estado una sola vez y libera inventario si el pago se rechaza/cancela."""
    with conn.cursor() as cursor:
        sql = "SELECT id,estado FROM tienda_pedidos WHERE referencia=%s"
        params = [reference]
        if id_usuario is not None:
            sql += " AND id_usuario=%s"
            params.append(id_usuario)
        sql += " FOR UPDATE"
        cursor.execute(sql, params)
        order = cursor.fetchone()
        if not order:
            return False
        current = str(order["estado"])
        if current == "pagado":
            return True
        final_without_payment = {"rechazado", "cancelado", "error_checkout"}
        if current in final_without_payment:
            return True
        if new_state in {"rechazado", "cancelado", "error_checkout"}:
            cursor.execute(
                "SELECT id_producto,cantidad FROM tienda_pedido_detalles WHERE id_pedido=%s",
                (order["id"],),
            )
            for line in cursor.fetchall():
                cursor.execute(
                    "UPDATE tienda_productos SET stock=stock+%s WHERE id=%s",
                    (int(line["cantidad"]), int(line["id_producto"])),
                )
        cursor.execute(
            "UPDATE tienda_pedidos SET estado=%s WHERE id=%s",
            (new_state, order["id"]),
        )
        return True


def _marcar_error(reference):
    conn = obtener_conexion()
    if not conn:
        return
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
        _cambiar_estado_pedido(conn, reference, "error_checkout")
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



@tienda_bp.route("/tienda/pedidos/<string:referencia>/verificar", methods=["GET"])
@requiere_autenticacion
def verificar_pedido(referencia):
    """Verifica el estado consultando la API del proveedor; nunca confía en query params de retorno."""
    transaction_id = request.args.get("transaction_id", "").strip()
    conn = obtener_conexion()
    if not conn:
        return _error("La base de datos no está disponible.", 503)
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute(
                """SELECT id, referencia, proveedor_pago, estado, total, moneda
                   FROM tienda_pedidos WHERE referencia=%s AND id_usuario=%s LIMIT 1""",
                (referencia, g.id_usuario),
            )
            pedido = cursor.fetchone()
            if not pedido:
                return _error("No encontramos ese pedido en tu cuenta.", 404)
            if pedido["estado"] in {"pagado", "rechazado", "cancelado", "error_checkout"}:
                return jsonify({"success": True, "referencia": referencia, "estado": pedido["estado"]}), 200
            proveedor = pedido["proveedor_pago"]
            total = Decimal(str(pedido["total"]))
            expected_cents = int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

        verified_status = None
        if proveedor == "mercadopago":
            token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
            if not token:
                return _error("La verificación de Mercado Pago no está configurada.", 503)
            try:
                response = requests.get(
                    "https://api.mercadopago.com/v1/payments/search",
                    params={"external_reference": referencia, "sort": "date_created", "criteria": "desc", "limit": 10},
                    headers={"Authorization": "Bearer " + token},
                    timeout=(3.05, 10),
                )
                response.raise_for_status()
                results = response.json().get("results", [])
                for payment in results:
                    if str(payment.get("external_reference") or "") != referencia:
                        continue
                    transaction_total = Decimal(str(payment.get("transaction_amount", "0"))).quantize(Decimal("0.01"))
                    if transaction_total != total or str(payment.get("currency_id") or "") != "COP":
                        continue
                    verified_status = payment.get("status")
                    if verified_status == "approved":
                        break
            except (requests.RequestException, ValueError, TypeError, InvalidOperation):
                return _error("No se pudo verificar el pago con Mercado Pago. Inténtalo de nuevo.", 503)
        elif proveedor == "wompi":
            private_key = os.environ.get("WOMPI_PRIVATE_KEY", "").strip()
            if not private_key:
                return _error("La verificación de Wompi no está configurada (falta WOMPI_PRIVATE_KEY).", 503)
            if not transaction_id or len(transaction_id) > 120:
                return _error("Falta el identificador de la transacción de Wompi para verificar el pago.", 400)
            api_base = os.environ.get("WOMPI_API_BASE", "https://sandbox.wompi.co/v1").rstrip("/")
            try:
                response = requests.get(
                    api_base + "/transactions/" + requests.utils.quote(transaction_id, safe=""),
                    headers={"Authorization": "Bearer " + private_key},
                    timeout=(3.05, 10),
                )
                response.raise_for_status()
                transaction = response.json().get("data", {})
                if str(transaction.get("reference") or "") != referencia:
                    return _error("La referencia de la transacción no coincide con el pedido.", 409)
                if int(transaction.get("amount_in_cents") or 0) != expected_cents or transaction.get("currency") != "COP":
                    return _error("El valor de la transacción no coincide con el pedido.", 409)
                verified_status = transaction.get("status")
            except (requests.RequestException, ValueError, TypeError):
                return _error("No se pudo verificar el pago con Wompi. Inténtalo de nuevo.", 503)
        else:
            return _error("Proveedor de pago no reconocido.", 409)

        state_map = {
            "approved": "pagado",
            "APPROVED": "pagado",
            "rejected": "rechazado",
            "DECLINED": "rechazado",
            "cancelled": "cancelado",
            "VOIDED": "cancelado",
            "pending": "pendiente_pago",
            "PENDING": "pendiente_pago",
            "in_process": "pendiente_pago",
            "ERROR": "pendiente_pago",
        }
        new_state = state_map.get(str(verified_status), "pendiente_pago")
        if not _cambiar_estado_pedido(conn, referencia, new_state, g.id_usuario):
            return _error("No encontramos ese pedido en tu cuenta.", 404)
        conn.commit()
        return jsonify({
            "success": True,
            "referencia": referencia,
            "estado": new_state,
            "mensaje": "Estado consultado directamente con la pasarela de pago."
        }), 200
    finally:
        conn.close()



def _aplicar_estado_notificacion(reference, proveedor, estado_proveedor, total_proveedor, moneda):
    try:
        total_pagado = Decimal(str(total_proveedor)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return False
    conn = obtener_conexion()
    if not conn:
        return False
    try:
        with conn.cursor() as cursor:
            _asegurar_tablas(cursor)
            cursor.execute(
                """SELECT total FROM tienda_pedidos
                   WHERE referencia=%s AND proveedor_pago=%s LIMIT 1""",
                (reference, proveedor),
            )
            order = cursor.fetchone()
            if not order or total_pagado != Decimal(str(order["total"])).quantize(Decimal("0.01")) or moneda != "COP":
                return False
        status_map = {
            "approved": "pagado", "APPROVED": "pagado",
            "rejected": "rechazado", "DECLINED": "rechazado",
            "cancelled": "cancelado", "VOIDED": "cancelado",
            "pending": "pendiente_pago", "PENDING": "pendiente_pago",
            "in_process": "pendiente_pago", "ERROR": "pendiente_pago",
        }
        new_state = status_map.get(str(estado_proveedor), "pendiente_pago")
        found = _cambiar_estado_pedido(conn, reference, new_state)
        if found:
            conn.commit()
        return bool(found)
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


@tienda_bp.route("/tienda/webhooks/mercadopago", methods=["POST"])
def webhook_mercadopago():
    """Consulta la transacción en la API autenticada de Mercado Pago antes de cambiar el pedido."""
    token = os.environ.get("MP_ACCESS_TOKEN", "").strip()
    if not token:
        return jsonify({"received": False, "error": "Proveedor no configurado."}), 503
    payload = request.get_json(silent=True) or {}
    payment_id = (payload.get("data") or {}).get("id") or request.args.get("data.id")
    if not payment_id or len(str(payment_id)) > 120:
        return jsonify({"received": True}), 200
    try:
        response = requests.get(
            "https://api.mercadopago.com/v1/payments/" + requests.utils.quote(str(payment_id), safe=""),
            headers={"Authorization": "Bearer " + token},
            timeout=(3.05, 10),
        )
        response.raise_for_status()
        payment = response.json()
        reference = str(payment.get("external_reference") or "")
        if not reference.startswith("FITAI-"):
            return jsonify({"received": True}), 200
        total = payment.get("transaction_amount")
        currency = str(payment.get("currency_id") or "")
        ok = _aplicar_estado_notificacion(reference, "mercadopago", payment.get("status"), total, currency)
        return jsonify({"received": True, "processed": ok}), 200
    except (requests.RequestException, ValueError, TypeError):
        return jsonify({"received": False, "error": "No se pudo verificar la notificación."}), 503


@tienda_bp.route("/tienda/webhooks/wompi", methods=["POST"])
def webhook_wompi():
    """Valida el evento consultando la transacción con la llave privada del comercio."""
    private_key = os.environ.get("WOMPI_PRIVATE_KEY", "").strip()
    if not private_key:
        return jsonify({"received": False, "error": "Proveedor no configurado."}), 503
    payload = request.get_json(silent=True) or {}
    transaction = ((payload.get("data") or {}).get("transaction") or {})
    transaction_id = transaction.get("id")
    if not transaction_id or len(str(transaction_id)) > 120:
        return jsonify({"received": True}), 200
    api_base = os.environ.get("WOMPI_API_BASE", "https://production.wompi.co/v1").rstrip("/")
    try:
        response = requests.get(
            api_base + "/transactions/" + requests.utils.quote(str(transaction_id), safe=""),
            headers={"Authorization": "Bearer " + private_key},
            timeout=(3.05, 10),
        )
        response.raise_for_status()
        verified = response.json().get("data", {})
        reference = str(verified.get("reference") or "")
        if not reference.startswith("FITAI-"):
            return jsonify({"received": True}), 200
        amount = Decimal(str(int(verified.get("amount_in_cents") or 0))) / Decimal("100")
        ok = _aplicar_estado_notificacion(reference, "wompi", verified.get("status"), amount, verified.get("currency"))
        return jsonify({"received": True, "processed": ok}), 200
    except (requests.RequestException, ValueError, TypeError, InvalidOperation):
        return jsonify({"received": False, "error": "No se pudo verificar la notificación."}), 503
