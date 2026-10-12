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
from backend.routes.tienda import _asegurar_inventario, _asegurar_tabla_envios

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
    cursor.execute("""CREATE TABLE IF NOT EXISTS pago_detalle_snapshot (
        id_pedido INT NOT NULL,
        id_prenda_catalogo INT NOT NULL,
        categoria VARCHAR(50) NULL,
        color VARCHAR(50) NULL,
        talla VARCHAR(20) NULL,
        estilo VARCHAR(50) NULL,
        temporada VARCHAR(30) NULL,
        url_imagen VARCHAR(500) NULL,
        PRIMARY KEY (id_pedido,id_prenda_catalogo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cursor.execute("""CREATE TABLE IF NOT EXISTS pago_carrito_snapshot (
        id_pedido INT NOT NULL,
        id_carrito INT NOT NULL,
        id_prenda INT NOT NULL,
        cantidad INT NOT NULL,
        PRIMARY KEY (id_pedido,id_carrito),
        INDEX idx_pago_carrito_prenda (id_prenda)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    _asegurar_inventario(cursor)
    _asegurar_tabla_envios(cursor)


def _liberar_stock_pedido(cursor, pedido_id):
    cursor.execute(
        "SELECT id_prenda_catalogo,cantidad FROM pedido_detalles WHERE id_pedido=%s",
        (pedido_id,),
    )
    for item in cursor.fetchall():
        cursor.execute(
            "UPDATE tienda_stock SET stock=stock+%s WHERE id_prenda=%s",
            (int(item["cantidad"]), int(item["id_prenda_catalogo"])),
        )


def _marcar_checkout_error(conn, pedido_id):
    """Marca error y libera stock reservado una sola vez."""
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id_pago,estado FROM pago_intentos WHERE id_pedido=%s FOR UPDATE",
                (pedido_id,),
            )
            payment = cursor.fetchone()
            if payment and payment["estado"] not in {"pagado", "rechazado", "anulado", "error"}:
                _liberar_stock_pedido(cursor, pedido_id)
                cursor.execute(
                    "UPDATE pago_intentos SET estado='error' WHERE id_pago=%s",
                    (payment["id_pago"],),
                )
                cursor.execute(
                    "UPDATE pedidos SET estado='error_pago' WHERE id_pedido=%s AND estado='pendiente_pago'",
                    (pedido_id,),
                )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("No se pudo liberar la reserva de stock del checkout fallido")


def _limpiar_carrito_snapshot(cursor, pedido_id, usuario_id):
    cursor.execute(
        "SELECT id_carrito,cantidad FROM pago_carrito_snapshot WHERE id_pedido=%s",
        (pedido_id,),
    )
    for snap in cursor.fetchall():
        cantidad = int(snap["cantidad"])
        cursor.execute(
            """UPDATE carrito SET cantidad=cantidad-%s
               WHERE id_carrito=%s AND id_usuario=%s AND cantidad>%s""",
            (cantidad, int(snap["id_carrito"]), usuario_id, cantidad),
        )
        if cursor.rowcount == 0:
            cursor.execute(
                "DELETE FROM carrito WHERE id_carrito=%s AND id_usuario=%s",
                (int(snap["id_carrito"]), usuario_id),
            )


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
    url = data.get("sandbox_init_point") if token.startswith("TEST-") else data.get("init_point")
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
    """Confirma el pago con datos consultados al proveedor y entrega de forma idempotente."""
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

            current_state = str(pago["estado"] or "").lower()
            provider_state = str(estado_proveedor or "").upper()
            terminal_states = {"pagado", "rechazado", "anulado", "error"}

            if current_state == "pagado" or pago["estado_pedido"] == "pagado":
                conn.commit()
                return True, "pagado"
            # Una notificación repetida no libera inventario dos veces ni revierte un estado final.
            if current_state in {"rechazado", "anulado", "error"}:
                conn.commit()
                return True, current_state

            if provider_state != "APPROVED":
                local_state = {
                    "DECLINED": "rechazado",
                    "VOIDED": "anulado",
                    "ERROR": "error",
                    "PENDING": "pendiente",
                    "IN_PROCESS": "pendiente",
                }.get(provider_state, "pendiente")
                if local_state in {"rechazado", "anulado", "error"}:
                    _liberar_stock_pedido(c, pago["id_pedido"])
                c.execute("""UPDATE pago_intentos SET estado=%s,
                             id_transaccion_proveedor=COALESCE(NULLIF(%s,''),id_transaccion_proveedor)
                             WHERE id_pago=%s""",
                          (local_state, str(transaccion_id or ""), pago["id_pago"]))
                c.execute("UPDATE pedidos SET estado=%s WHERE id_pedido=%s AND estado <> 'pagado'",
                          (local_state, pago["id_pedido"]))
                conn.commit()
                return True, local_state

            # Snapshot independiente del catálogo: un cambio/borrado posterior no bloquea la entrega.
            c.execute("""SELECT d.id_prenda_catalogo,d.nombre_prenda,d.precio,d.cantidad,
                                s.categoria,s.color,s.talla,s.estilo,s.temporada,s.url_imagen
                         FROM pedido_detalles d
                         JOIN pago_detalle_snapshot s
                           ON s.id_pedido=d.id_pedido AND s.id_prenda_catalogo=d.id_prenda_catalogo
                         WHERE d.id_pedido=%s""", (pago["id_pedido"],))
            detalles = c.fetchall()
            if not detalles:
                raise RuntimeError("No hay snapshot de prendas para entregar el pedido.")
            for item in detalles:
                if not item.get("categoria"):
                    raise RuntimeError("El snapshot de una prenda no tiene categoría.")
                for _ in range(int(item["cantidad"])):
                    c.execute("""INSERT INTO prendas
                        (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (pago["id_usuario"], item["nombre_prenda"], item["categoria"], item["color"],
                         item["talla"], item["estilo"], item["temporada"], item["url_imagen"], item["precio"]))
            c.execute("UPDATE pago_intentos SET estado='pagado', id_transaccion_proveedor=%s WHERE id_pago=%s",
                      (str(transaccion_id or ""), pago["id_pago"]))
            c.execute("UPDATE pedidos SET estado='pagado' WHERE id_pedido=%s", (pago["id_pedido"],))
            _limpiar_carrito_snapshot(c, pago["id_pedido"], pago["id_usuario"])
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
    if not isinstance(data, dict):
        return jsonify({"error": "El cuerpo debe ser un objeto JSON."}), 400
    proveedor = str(data.get("proveedor", "")).strip().lower()
    envio = data.get("envio") or {}
    if not isinstance(envio, dict):
        return jsonify({"error": "Los datos de envío no tienen formato válido."}), 400
    campos_envio = ("nombre", "email", "telefono", "direccion", "ciudad", "departamento")
    envio = {key: str(envio.get(key, "")).strip()[:255] for key in campos_envio}
    if any(not envio[key] for key in campos_envio) or "@" not in envio["email"]:
        return jsonify({"error": "Completa todos los datos de entrega con un correo válido."}), 400
    if (len(envio["nombre"]) > 120 or len(envio["email"]) > 180 or len(envio["telefono"]) > 40
            or len(envio["ciudad"]) > 100 or len(envio["departamento"]) > 100):
        return jsonify({"error": "Uno o más datos de entrega superan el tamaño permitido."}), 400
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
            c.execute("""SELECT ca.id_carrito,ca.id_prenda,ca.cantidad,
                                pr.id_prenda,pr.nombre_prenda,pr.precio,pr.categoria,pr.color,
                                pr.talla,pr.estilo,pr.temporada,pr.url_imagen,
                                ts.stock,ts.activo
                         FROM carrito ca
                         JOIN prendas pr ON pr.id_prenda=ca.id_prenda
                         LEFT JOIN tienda_stock ts ON ts.id_prenda=pr.id_prenda
                         WHERE ca.id_usuario=%s AND pr.id_usuario IS NULL
                         ORDER BY ca.fecha_agregado ASC FOR UPDATE""", (g.id_usuario,))
            items = c.fetchall()
            if not items:
                return jsonify({"error": "Tu carrito está vacío."}), 400

            precio_minimo = float(os.environ.get("FITAI_MIN_CHECKOUT_COP", "1000"))
            if any(not x.get("precio") or float(x["precio"]) < precio_minimo for x in items):
                return jsonify({"error": "Hay prendas con precio no válido para un cobro en COP. Revisa los precios reales antes de cobrar."}), 409
            total = round(sum(float(x["precio"]) * int(x["cantidad"]) for x in items), 2)
            if total < precio_minimo:
                return jsonify({"error": "El total del pedido no alcanza el mínimo permitido en COP."}), 409
            if total <= 0 or total > MAX_TOTAL_COP:
                return jsonify({"error": "El total del pedido está fuera del límite permitido."}), 400

            current_snapshot = sorted(
                (int(x["id_carrito"]), int(x["id_prenda"]), int(x["cantidad"])) for x in items
            )
            # Idempotencia por usuario: no crea otro cobro mientras exista uno pendiente.
            c.execute("""SELECT pi.*,p.total
                         FROM pago_intentos pi JOIN pedidos p ON p.id_pedido=pi.id_pedido
                         WHERE p.id_usuario=%s AND p.estado='pendiente_pago'
                           AND pi.estado IN ('creando','pendiente')
                         ORDER BY pi.id_pago DESC LIMIT 1 FOR UPDATE""", (g.id_usuario,))
            pending = c.fetchone()
            if pending:
                c.execute("""SELECT id_carrito,id_prenda,cantidad FROM pago_carrito_snapshot
                             WHERE id_pedido=%s ORDER BY id_carrito""", (pending["id_pedido"],))
                previous_snapshot = sorted(
                    (int(x["id_carrito"]), int(x["id_prenda"]), int(x["cantidad"])) for x in c.fetchall()
                )
                if previous_snapshot != current_snapshot:
                    return jsonify({"error": "Ya tienes un checkout pendiente. Termina o espera a que se resuelva antes de cambiar el carrito e iniciar otro pago."}), 409
                if pending["proveedor"] == proveedor and pending.get("url_checkout"):
                    return jsonify({
                        "success": True, "pedido_id": int(pending["id_pedido"]),
                        "referencia": pending["referencia"], "proveedor": proveedor,
                        "estado": "pendiente_pago", "total": float(pending["total"]),
                        "moneda": "COP", "checkout_url": pending["url_checkout"],
                        "reutilizado": True,
                    }), 200
                return jsonify({"error": "Ya existe un checkout para este carrito. Continúa con el mismo método de pago para evitar un cobro duplicado."}), 409

            if any(x.get("stock") is None or not bool(x.get("activo")) or int(x.get("stock") or 0) < int(x["cantidad"]) for x in items):
                return jsonify({"error": "Una o más prendas están agotadas o no disponibles. Actualiza el carrito antes de pagar."}), 409

            monto_centavos = int(round(total * 100))
            # Reserva inventario dentro de la misma transacción que crea el pedido.
            for item in items:
                c.execute("""UPDATE tienda_stock SET stock=stock-%s
                             WHERE id_prenda=%s AND activo=1 AND stock >= %s""",
                          (int(item["cantidad"]), int(item["id_prenda"]), int(item["cantidad"])))
                if c.rowcount != 1:
                    conn.rollback()
                    return jsonify({"error": "El inventario cambió mientras preparábamos el pedido. Actualiza el carrito e inténtalo de nuevo."}), 409

            c.execute("INSERT INTO pedidos(id_usuario,total,estado) VALUES(%s,%s,'pendiente_pago')",
                      (g.id_usuario, total))
            pedido_id = int(c.lastrowid)
            c.execute("INSERT INTO pedido_envios (id_pedido,nombre,email,telefono,direccion,ciudad,departamento) VALUES(%s,%s,%s,%s,%s,%s,%s)", (pedido_id, envio["nombre"], envio["email"], envio["telefono"], envio["direccion"], envio["ciudad"], envio["departamento"]))
            for item in items:
                c.execute("""INSERT INTO pedido_detalles
                    (id_pedido,id_prenda_catalogo,nombre_prenda,precio,cantidad)
                    VALUES(%s,%s,%s,%s,%s)""",
                    (pedido_id, item["id_prenda"], item["nombre_prenda"], item["precio"], item["cantidad"]))
                c.execute("""INSERT INTO pago_detalle_snapshot
                    (id_pedido,id_prenda_catalogo,categoria,color,talla,estilo,temporada,url_imagen)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (pedido_id, item["id_prenda"], item.get("categoria"), item.get("color"),
                     item.get("talla"), item.get("estilo"), item.get("temporada"), item.get("url_imagen")))
                c.execute("""INSERT INTO pago_carrito_snapshot
                    (id_pedido,id_carrito,id_prenda,cantidad) VALUES(%s,%s,%s,%s)""",
                    (pedido_id, item["id_carrito"], item["id_prenda"], item["cantidad"]))
            referencia = f"FITAI-{pedido_id}-{secrets.token_hex(6)}"
            c.execute("""INSERT INTO pago_intentos
                (id_pedido,proveedor,referencia,monto_centavos,moneda,estado)
                VALUES(%s,%s,%s,%s,'COP','creando')""",
                (pedido_id, proveedor, referencia, monto_centavos))
        conn.commit()

        if proveedor == "mercadopago":
            checkout_url, provider_id = _crear_checkout_mercadopago(referencia, pedido_id, total, items)
        else:
            checkout_url, provider_id = _crear_checkout_wompi(referencia, pedido_id, monto_centavos)

        with conn.cursor() as c:
            c.execute("""UPDATE pago_intentos SET estado='pendiente',url_checkout=%s,
                         id_transaccion_proveedor=NULLIF(%s,'') WHERE referencia=%s AND estado='creando'""",
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
            _marcar_checkout_error(conn, pedido_id)
        return jsonify({"error": str(exc)}), 503
    except requests.RequestException:
        conn.rollback()
        if pedido_id:
            _marcar_checkout_error(conn, pedido_id)
        logger.exception("Error de red creando checkout")
        return jsonify({"error": "La pasarela no respondió. Se liberó el inventario reservado; vuelve a intentarlo."}), 502
    except Exception:
        conn.rollback()
        if pedido_id:
            _marcar_checkout_error(conn, pedido_id)
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
        if payment.get("currency_id") != "COP":
            return jsonify({"received": True, "verified": False}), 200
        if not referencia or not monto:
            return jsonify({"received": True}), 200
        ok, state = _marcar_pago_y_entregar(
            referencia, "mercadopago", str(payment_id), payment.get("status"), monto
        )
        if not ok and state in {"database_unavailable", "fulfillment_failed", "reference_not_found"}:
            return jsonify({"error": "La confirmación no pudo guardarse; se necesita reintento del proveedor."}), 503
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
        if verified.get("currency") != "COP":
            return jsonify({"received": True, "verified": False}), 200
        if not referencia or not monto:
            return jsonify({"received": True}), 200
        ok, state = _marcar_pago_y_entregar(
            referencia, "wompi", str(transaction_id), verified.get("status"), monto
        )
        if not ok and state in {"database_unavailable", "fulfillment_failed", "reference_not_found"}:
            return jsonify({"error": "La confirmación no pudo guardarse; se necesita reintento del proveedor."}), 503
        if not ok:
            return jsonify({"received": True, "verified": False}), 200
        return jsonify({"received": True, "estado": state}), 200
    except requests.RequestException:
        logger.exception("No se pudo consultar Wompi desde el webhook")
        return jsonify({"error": "Error temporal verificando el pago."}), 503
