"""Generación experimental de prendas 3D mediante Meshy Image-to-3D.

La clave del proveedor se lee exclusivamente desde MESHY_API_KEY en el servidor.
Las tareas se vinculan al usuario autenticado para impedir consultas cruzadas.
"""
import base64
import binascii
import os
import re

import cv2
import numpy as np
import requests
from flask import Blueprint, current_app, g, jsonify, request

from backend.auth.tokens import requiere_autenticacion
from backend.config import Config
from backend.database.conexion import obtener_conexion
from backend.security import limiter

ropa_3d_bp = Blueprint("ropa_3d", __name__)
MESHY_API = "https://api.meshy.ai/openapi/v1"
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_BYTES = min(int(getattr(Config, "MAX_CONTENT_LENGTH", 10 * 1024 * 1024)), 10 * 1024 * 1024)


def _asegurar_tabla(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ropa_generaciones_3d (
            task_id VARCHAR(100) PRIMARY KEY,
            id_usuario INT NOT NULL,
            categoria VARCHAR(32) NOT NULL,
            fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_ropa3d_usuario (id_usuario, fecha_creacion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def _leer_imagen_data_url(value):
    if not isinstance(value, str) or len(value) > ((MAX_IMAGE_BYTES * 4 // 3) + 256):
        return None, "La imagen está vacía o supera el límite de 10 MB."
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/]+={0,2})", value)
    if not match or match.group(1) not in ALLOWED_MIME:
        return None, "Envía una imagen JPG, PNG o WebP válida."
    try:
        raw = base64.b64decode(match.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None, "La codificación de la imagen no es válida."
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        return None, "La imagen está vacía o supera el límite de 10 MB."
    decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if decoded is None:
        return None, "El archivo no contiene una imagen válida."
    return value, None


@ropa_3d_bp.route("/ropa/3d/generar", methods=["POST"])
@requiere_autenticacion
@limiter.limit("3 per hour")
def generar_prenda_3d():
    api_key = os.environ.get("MESHY_API_KEY", "").strip()
    if not api_key:
        return jsonify({
            "error": "La generación 3D aún no está configurada. Falta MESHY_API_KEY en las variables de entorno del backend."
        }), 503

    if request.mimetype == "multipart/form-data":
        category = request.form.get("categoria", "shirts")
        uploaded = request.files.get("imagen")
        if not uploaded:
            return jsonify({"error": "Selecciona una imagen para generar la prenda."}), 400
        mime = (uploaded.mimetype or "").lower()
        raw = uploaded.read(MAX_IMAGE_BYTES + 1)
        if mime not in ALLOWED_MIME:
            return jsonify({"error": "Envía una imagen JPG, PNG o WebP válida."}), 400
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            return jsonify({"error": "La imagen está vacía o supera el límite de 10 MB."}), 400
        if cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR) is None:
            return jsonify({"error": "El archivo no contiene una imagen válida."}), 400
        image_data = f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")
    else:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "Envía un objeto JSON o un archivo de imagen válido."}), 400
        category = data.get("categoria", "shirts")
        image_data, error = _leer_imagen_data_url(data.get("imagen"))
        if error:
            return jsonify({"error": error}), 400

    if category not in {"shirts", "pants", "accessories"}:
        return jsonify({"error": "La categoría debe ser shirts, pants o accessories."}), 400

    try:
        response = requests.post(
            f"{MESHY_API}/image-to-3d",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "image_url": image_data,
                "model_type": "standard",
                "should_texture": True,
                "target_formats": ["glb"]
            },
            timeout=(10, 60)
        )
    except requests.RequestException:
        current_app.logger.warning("No se pudo conectar con el proveedor de generación 3D.")
        return jsonify({"error": "No se pudo conectar con el servicio 3D. Inténtalo de nuevo más tarde."}), 502

    if response.status_code not in (200, 201):
        if response.status_code == 401:
            current_app.logger.error("Meshy rechazó la clave MESHY_API_KEY.")
            return jsonify({"error": "La clave del servicio 3D no es válida. Revisa MESHY_API_KEY en Render."}), 502
        if response.status_code == 402:
            return jsonify({"error": "El servicio 3D no tiene créditos disponibles. Revisa el plan y el saldo antes de volver a intentarlo."}), 402
        if response.status_code == 429:
            return jsonify({"error": "El servicio 3D está limitando las solicitudes. Espera un momento."}), 429
        current_app.logger.warning("Proveedor 3D devolvió HTTP %s.", response.status_code)
        return jsonify({"error": "El proveedor 3D no pudo aceptar la imagen."}), 502

    try:
        payload = response.json()
        task_id = payload.get("result") or payload.get("id")
    except ValueError:
        task_id = None
    if not isinstance(task_id, str) or not task_id or len(task_id) > 100:
        current_app.logger.warning("Respuesta del proveedor 3D sin identificador de tarea válido.")
        return jsonify({"error": "El servicio 3D devolvió una respuesta inesperada."}), 502

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "La base de datos no está disponible para registrar la tarea."}), 503
    try:
        with conn.cursor() as cursor:
            _asegurar_tabla(cursor)
            cursor.execute(
                "INSERT INTO ropa_generaciones_3d (task_id, id_usuario, categoria) VALUES (%s, %s, %s)",
                (task_id, g.id_usuario, category)
            )
        conn.commit()
        return jsonify({
            "task_id": task_id,
            "status": "PENDING",
            "categoria": category,
            "mensaje": "Generación iniciada. Consulta el estado en unos momentos."
        }), 202
    except Exception:
        conn.rollback()
        current_app.logger.exception("No se pudo registrar la tarea 3D.")
        return jsonify({"error": "No se pudo registrar la generación 3D."}), 500
    finally:
        conn.close()


@ropa_3d_bp.route("/ropa/3d/tareas/<task_id>", methods=["GET"])
@requiere_autenticacion
@limiter.limit("60 per hour")
def consultar_prenda_3d(task_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", task_id or ""):
        return jsonify({"error": "El identificador de tarea no es válido."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "La base de datos no está disponible."}), 503
    try:
        with conn.cursor() as cursor:
            _asegurar_tabla(cursor)
            cursor.execute(
                "SELECT categoria FROM ropa_generaciones_3d WHERE task_id=%s AND id_usuario=%s",
                (task_id, g.id_usuario)
            )
            owned_task = cursor.fetchone()
        if not owned_task:
            return jsonify({"error": "No se encontró esa tarea 3D para tu cuenta."}), 404
        category = owned_task.get("categoria") if isinstance(owned_task, dict) else owned_task[0]
    finally:
        conn.close()

    api_key = os.environ.get("MESHY_API_KEY", "").strip()
    if not api_key:
        return jsonify({"error": "La generación 3D no está configurada en el servidor."}), 503

    try:
        response = requests.get(
            f"{MESHY_API}/image-to-3d/{task_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(10, 30)
        )
    except requests.RequestException:
        return jsonify({"error": "No se pudo consultar el estado del servicio 3D."}), 502

    if response.status_code != 200:
        current_app.logger.warning("Consulta de tarea 3D falló con HTTP %s.", response.status_code)
        return jsonify({"error": "No se pudo consultar la tarea 3D."}), 502
    try:
        task = response.json()
    except ValueError:
        return jsonify({"error": "El servicio 3D devolvió una respuesta inesperada."}), 502

    model_urls = task.get("model_urls") or {}
    return jsonify({
        "task_id": task_id,
        "status": task.get("status", "UNKNOWN"),
        "progress": task.get("progress", 0),
        "categoria": category,
        "model_url": model_urls.get("glb") if task.get("status") == "SUCCEEDED" else None,
        "error": (task.get("task_error") or {}).get("message") if task.get("status") == "FAILED" else None
    }), 200
