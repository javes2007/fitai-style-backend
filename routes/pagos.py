"""Checkout seguro para compras propias de FitAI Style.

Las claves privadas solo se leen del entorno del servidor. El navegador nunca
puede declarar un pedido pagado: el estado se confirma consultando la API del
proveedor desde los webhooks.
"""
import hashlib
import logging
import os
import secrets
from urllib.parse import urlencode

import requests
from flask import Blueprint, jsonify, request, g

from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion
from backend.routes.compras import _asegurar_tablas

pagos_bp = Blueprint("pagos", __name__)
logger = logging.getLogger(__name__)

FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://fitai-style-frontend.vercel.app").rstrip("/")
BACKEND_URL = os.environ.get("PUBLIC_BACKEND_URL", os.environ.get("RENDER_EXTERNAL_URL", "https://fitai-style-backend.onrender.com")).rstrip("/")
MAX_TOTAL_COP = 20_000_000


def _asegurar_tabla_pagos(cursor):
    cursor.execute("""CREATE TABLE IF NOT EXISTS pago_intentos (
        id_pago INT AUTO_INCREMENT PRIMARY KEY,
        id_pedido INT NOT NULL,
        proveedor VARCHAR(24) NOT NULL,
        referencia VARCHAR(100) NOT NULL UNIQUE,
        monto_centavos BIGINT NOT NULL,
        moneda CHAR(3) NOT NULL DEFAULT 'COP',
        estado VARCHAR(24) NOT NULL DEFAULT 'pendiente',
        url_checkout VARCHAR(1000) NULL,
        id_transaccion_proveedor VARCHAR(150) NULL,
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_pago_pedido (id_pedido),
        INDEX idx_pago_proveedor_transaccion (proveedor,id_transaccion_proveedor)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")


def _crear_checkout_mercadopago(referencia, pedido_id, monto, items):
    token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MERCADOPAGO_ACCESS_TOKEN no está configurada en el backend.")
    payload = {
        "items": [{
            "id": str(item["id_prenda"]),
            "title": str(item["nombre_prenda"])[:250],
            "quantity": int(item["cantidad"]),
            "currency_id": "COP",
            "unit_price": round(float(item["precio"]), 2),
        } for item in items],
        "external_reference": referencia,
        "notification_url": f"{BACKEND_URL}/api/pagos/webhook/mercadopago",
        "back_urls": {
            "success": f"{FRONTEND_URL}/tienda.html?pedido={pedido_id}&resultado=retorno",
            "pending": f"{FRONTEND_URL}/tienda.html?pedido={pedido_id}&resultado=retorno",
            "failure": f"{FRONTEND_URL}/tienda.html?pedido={pedido_id}&resultado=retorno",
        },
        "auto_return": "approved",
        "metadata": {"fitai_order_id": pedido_id, "fitai_reference": referencia},
    }
    response = requests.post(
        "https://api.mercadopago.com/checkout/preferences",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=(5, 15),
    )
    if not response.ok:
        logger.warning("Mercado Pago no creó checkout: HTTP %s", response.status_code)
        raise RuntimeError("Mercado Pago no pudo crear el checkout. Verifica las credenciales y la cuenta.")
    data = response.json()
    url = data.get("init_point")
    if not url:
        raise RuntimeError("Mercado Pago no devolvió una URL de pago válida.")
    return url, str(data.get("id") or "")


def _crear_checkout_wompi(referencia, pedido_id, monto_centavos):
    public_key = os.environ.get("WOMPI_PUBLIC_KEY", "").strip()
    integrity_secret = os.environ.get("WOMPI_INTEGRITY_SECRET", "").strip()
    if not public_key or not integrity_secret:
        raise RuntimeError("Configura WOMPI_PUBLIC_KEY y WOMPI_INTEGRITY_SECRET en el backend.")
    firma_base = f"{referencia}{monto_centavos}COP{integrity_secret}"
    firma = hashlib.sha256(firma_base.encode("utf-8")).hexdigest()
    redirect_url = f"{FRONTEND_URL}/tienda.html?pedido={pedido_id}&resultado=retorno"
    params = {
        "public-key": public_key,
        "currency": "COP",
        "amount-in-cents": str(monto_centavos),
        "reference": referencia,
        "signature:integrity": firma,
        "redirect-url": redirect_url,
    }
    return "https://checkout.wompi.co/p/?" + urlencode(params), ""


def _marcar_pago_y_entregar(referencia, proveedor, transaccion_id, estado_proveedor, monto_centavos):
    """Actualiza el estado solo después de verificar la transacción con el proveedor."""
    conn = obtener_conexion()
    if not conn:
        return False, "database_unavailable"
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            _asegurar_tabla_pagos(c)
            c.execute("""SELECT pi.*, p.id_usuario, p.estado AS estado_pedido
                         FROM pago_intentos pi JOIN pedidos p ON p.id_pedido=pi.id_pedido
                         WHERE pi.referencia=%s AND pi.proveedor=%s FOR UPDATE""",
                      (referencia, proveedor))
            pago = c.fetchone()
            if not pago:
                conn.rollback()
                return False, "reference_not_found"
            if int(pago["monto_centavos"]) != int(monto_centavos):
                conn.rollback()
                return False, "amount_mismatch"

            estado = str(estado_proveedor or "").upper()
            if estado != "APPROVED":
                estado_local = {
                    "DECLINED": "rechazado",
                    "VOIDED": "anulado",
                    "ERROR": "error",
                    "PENDING": "pendiente",
                }.get(estado, "pendiente")
                c.execute("""UPDATE pago_intentos SET estado=%s,
                             id_transaccion_proveedor=COALESCE(NULLIF(%s,''),id_transaccion_proveedor)
                             WHERE id_pago=%s""", (estado_local, str(transaccion_id or ""), pago["id_pago"]))
                c.execute("UPDATE pedidos SET estado=%s WHERE id_pedido=%s AND estado <> 'pagado'",
                          (estado_local, pago["id_pedido"]))
                conn.commit()
                return True, estado_local

            # Idempotencia: un webhook repetido nunca entrega dos veces.
            if pago["estado"] == "pagado" or pago["estado_pedido"] == "pagado":
                conn.commit()
                return True, "pagado"

            c.execute("""SELECT d.id_prenda_catalogo,d.nombre_prenda,d.precio,d.cantidad,
                                pr.categoria,pr.color,pr.talla,pr.estilo,pr.temporada,pr.url_imagen
                         FROM pedido_detalles d LEFT JOIN prendas pr
                           ON pr.id_prenda=d.id_prenda_catalogo AND pr.id_usuario IS NULL
                         WHERE d.id_pedido=%s""", (pago["id_pedido"],))
            detalles = c.fetchall()
            for item in detalles:
                if not item.get("categoria"):
                    # No se marca como entregado si no se puede reconstruir el artículo.
                    raise RuntimeError("No se pudo localizar una prenda del pedido para entregarla.")
                for _ in range(int(item["cantidad"])):
                    c.execute("""INSERT INTO prendas
                        (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (pago["id_usuario"], item["nombre_prenda"], item["categoria"], item["color"],
                         item["talla"], item["estilo"], item["temporada"], item["url_imagen"], item["precio"]))
            c.execute("UPDATE pago_intentos SET estado='pagado', id_transaccion_proveedor=%s WHERE id_pago=%s",
                      (str(transaccion_id or ""), pago["id_pago"]))
            c.execute("UPDATE pedidos SET estado='pagado' WHERE id_pedido=%s", (pago["id_pedido"],))
            c.execute("DELETE FROM carrito WHERE id_usuario=%s", (pago["id_usuario"],))
        conn.commit()
        return True, "pagado"
    except Exception:
        conn.rollback()
        logger.exception("No se pudo actualizar/entregar el pedido tras el pago")
        return False, "fulfillment_failed"
    finally:
        conn.close()


@pagos_bp.route("/pagos/checkout", methods=["POST"])
@requiere_autenticacion
def iniciar_checkout():
    data = request.get_json(silent=True) or {}
    proveedor = str(data.get("proveedor", "")).strip().lower()
    if proveedor not in {"mercadopago", "wompi"}:
        return jsonify({"error": "Proveedor no válido. Elige mercadopago o wompi."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    pedido_id = None

    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            _asegurar_tabla_pagos(c)
            c.execute("""SELECT pr.id_prenda,pr.nombre_prenda,pr.precio,ca.cantidad
                         FROM carrito ca JOIN prendas pr ON pr.id_prenda=ca.id_prenda
                         WHERE ca.id_usuario=%s AND pr.id_usuario IS NULL
                         ORDER BY ca.fecha_agregado ASC FOR UPDATE""", (g.id_usuario,))
            items = c.fetchall()
            if not items:
                return jsonify({"error": "Tu carrito está vacío."}), 400
            if any(not x.get("precio") or float(x["precio"]) <= 0 for x in items):
                return jsonify({"error": "Hay prendas con precio inválido en el carrito."}), 409
            total = round(sum(float(x["precio"]) * int(x["cantidad"]) for x in items), 2)
            if total < float(os.environ.get("FITAI_MIN_CHECKOUT_COP", "1000")):
                return jsonify({"error": "Los precios del catálogo deben estar expresados en pesos colombianos completos (COP). Revisa el precio de las prendas antes de activar el cobro."}), 409
            if total <= 0 or total > MAX_TOTAL_COP:
                return jsonify({"error": "El total del pedido está fuera del límite permitido."}), 400
            monto_centavos = int(round(total * 100))
            c.execute("INSERT INTO pedidos(id_usuario,total,estado) VALUES(%s,%s,'pendiente_pago')",
                      (g.id_usuario, total))
            pedido_id = int(c.lastrowid)
            for item in items:
                c.execute("""INSERT INTO pedido_detalles
                    (id_pedido,id_prenda_catalogo,nombre_prenda,precio,cantidad)
                    VALUES(%s,%s,%s,%s,%s)""",
                    (pedido_id, item["id_prenda"], item["nombre_prenda"], item["precio"], item["cantidad"]))
            referencia = f"FITAI-{pedido_id}-{secrets.token_hex(6)}"
            c.execute("""INSERT INTO pago_intentos
                (id_pedido,proveedor,referencia,monto_centavos,moneda,estado)
                VALUES(%s,%s,%s,%s,'COP','creando')""",
                (pedido_id, proveedor, referencia, monto_centavos))
        conn.commit()
        # Llamar a la pasarela fuera de la transacción SQL.
        if proveedor == "mercadopago":
            checkout_url, provider_id = _crear_checkout_mercadopago(referencia, pedido_id, total, items)
        else:
            checkout_url, provider_id = _crear_checkout_wompi(referencia, pedido_id, monto_centavos)

        with conn.cursor() as c:
            c.execute("""UPDATE pago_intentos SET estado='pendiente',url_checkout=%s,
                         id_transaccion_proveedor=NULLIF(%s,'') WHERE referencia=%s""",
                      (checkout_url, provider_id, referencia))
        conn.commit()
        return jsonify({
            "success": True, "pedido_id": pedido_id, "referencia": referencia,
            "proveedor": proveedor, "estado": "pendiente_pago", "total": total,
            "moneda": "COP", "checkout_url": checkout_url,
        }), 201
    except RuntimeError as exc:
        conn.rollback()
        if pedido_id:
            try:
                with conn.cursor() as c:
                    c.execute("UPDATE pago_intentos SET estado='error' WHERE id_pedido=%s AND estado='creando'", (pedido_id,))
                    c.execute("UPDATE pedidos SET estado='error_pago' WHERE id_pedido=%s AND estado='pendiente_pago'", (pedido_id,))
                conn.commit()
            except Exception:
                conn.rollback()
        return jsonify({"error": str(exc)}), 503
    except requests.RequestException:
        conn.rollback()
        if pedido_id:
            try:
                with conn.cursor() as c:
                    c.execute("UPDATE pago_intentos SET estado='error' WHERE id_pedido=%s AND estado='creando'", (pedido_id,))
                    c.execute("UPDATE pedidos SET estado='error_pago' WHERE id_pedido=%s AND estado='pendiente_pago'", (pedido_id,))
                conn.commit()
            except Exception:
                conn.rollback()
        logger.exception("Error de red creando checkout")
        return jsonify({"error": "La pasarela no respondió. El pedido no se ha marcado como pagado; vuelve a intentarlo."}), 502
    except Exception:
        conn.rollback()
        if pedido_id:
            try:
                with conn.cursor() as c:
                    c.execute("UPDATE pago_intentos SET estado='error' WHERE id_pedido=%s AND estado='creando'", (pedido_id,))
                    c.execute("UPDATE pedidos SET estado='error_pago' WHERE id_pedido=%s AND estado='pendiente_pago'", (pedido_id,))
                conn.commit()
            except Exception:
                conn.rollback()
        logger.exception("No se pudo iniciar el checkout")
        return jsonify({"error": "No se pudo iniciar el pago. Revisa el carrito e inténtalo de nuevo."}), 500
    finally:
        conn.close()


@pagos_bp.route("/pagos/estado/<int:pedido_id>", methods=["GET"])
@requiere_autenticacion
def estado_pedido(pedido_id):
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            _asegurar_tabla_pagos(c)
            c.execute("""SELECT p.id_pedido,p.total,p.estado,p.fecha_creacion,
                                pi.proveedor,pi.referencia,pi.estado AS estado_pago
                         FROM pedidos p LEFT JOIN pago_intentos pi ON pi.id_pedido=p.id_pedido
                         WHERE p.id_pedido=%s AND p.id_usuario=%s
                         ORDER BY pi.id_pago DESC LIMIT 1""", (pedido_id, g.id_usuario))
            pedido = c.fetchone()
            if not pedido:
                return jsonify({"error": "Pedido no encontrado."}), 404
            pedido["total"] = float(pedido["total"])
            return jsonify(pedido), 200
    finally:
        conn.close()


@pagos_bp.route("/pagos/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():
    data = request.get_json(silent=True) or {}
    payment_id = (data.get("data") or {}).get("id") or request.args.get("data.id") or request.args.get("id")
    event_type = data.get("type") or request.args.get("type")
    if not payment_id or (event_type and event_type not in {"payment", "payment.created", "payment.updated"}):
        return jsonify({"received": True}), 200
    token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        return jsonify({"error": "Pasarela no configurada."}), 503
    try:
        response = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {token}"}, timeout=(5, 12),
        )
        if not response.ok:
            return jsonify({"error": "No se pudo verificar el pago con Mercado Pago."}), 502
        payment = response.json()
        referencia = str(payment.get("external_reference") or "")
        monto = int(round(float(payment.get("transaction_amount") or 0) * 100))
        if not referencia or not monto:
            return jsonify({"received": True}), 200
        ok, state = _marcar_pago_y_entregar(
            referencia, "mercadopago", str(payment_id), payment.get("status"), monto
        )
        if not ok:
            return jsonify({"received": True, "verified": False}), 200
        return jsonify({"received": True, "estado": state}), 200
    except requests.RequestException:
        logger.exception("No se pudo consultar Mercado Pago desde el webhook")
        return jsonify({"error": "Error temporal verificando el pago."}), 503


@pagos_bp.route("/pagos/webhook/wompi", methods=["POST"])
def webhook_wompi():
    data = request.get_json(silent=True) or {}
    event_data = data.get("data") or {}
    transaction = event_data.get("transaction") or {}
    transaction_id = transaction.get("id")
    if not transaction_id:
        return jsonify({"received": True}), 200
    private_key = os.environ.get("WOMPI_PRIVATE_KEY", "").strip()
    if not private_key:
        return jsonify({"error": "Pasarela no configurada."}), 503
    base_url = "https://sandbox.wompi.co/v1" if private_key.startswith("prv_test_") else "https://production.wompi.co/v1"
    try:
        response = requests.get(
            f"{base_url}/transactions/{transaction_id}",
            headers={"Authorization": f"Bearer {private_key}", "Accept": "application/json"},
            timeout=(5, 12),
        )
        if not response.ok:
            return jsonify({"error": "No se pudo verificar el pago con Wompi."}), 502
        verified = (response.json() or {}).get("data") or {}
        referencia = str(verified.get("reference") or "")
        monto = int(verified.get("amount_in_cents") or 0)
        if not referencia or not monto:
            return jsonify({"received": True}), 200
        ok, state = _marcar_pago_y_entregar(
            referencia, "wompi", str(transaction_id), verified.get("status"), monto
        )
        if not ok:
            return jsonify({"received": True, "verified": False}), 200
        return jsonify({"received": True, "estado": state}), 200
    except requests.RequestException:
        logger.exception("No se pudo consultar Wompi desde el webhook")
        return jsonify({"error": "Error temporal verificando el pago."}), 503
