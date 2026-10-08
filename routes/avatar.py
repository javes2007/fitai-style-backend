from flask import Blueprint, request, jsonify, g
from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion
import os
import uuid
import json
import cv2
import numpy as np

from backend.config import Config
from backend.ia.mediapipe_ai import analizar_medidas
from backend.ia.avatar_engine import build_avatar_dna
from backend.ia.recomendador import generar_recomendacion
from backend.utils import cache


avatar_bp = Blueprint(
    "avatar",
    __name__
)


ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "webp"
}


def allowed_file(filename):

    return (
        bool(filename)
        and "." in filename
        and filename.rsplit(
            ".",
            1
        )[1].lower() in ALLOWED_EXTENSIONS
    )


def _asegurar_perfil_avatar(c):
    c.execute("""
        CREATE TABLE IF NOT EXISTS avatar_perfiles (
            id_avatar INT AUTO_INCREMENT PRIMARY KEY,
            id_usuario INT NOT NULL UNIQUE,
            edad INT NULL,
            estilo VARCHAR(50) NULL,
            cuerpo JSON NULL,
            rostro JSON NULL,
            cabello JSON NULL,
            estetica JSON NULL,
            foto_analizada BOOLEAN NOT NULL DEFAULT FALSE,
            avatar_dna JSON NULL,
            fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)

@avatar_bp.route("/avatar/perfil", methods=["GET"])
@requiere_autenticacion
def obtener_perfil_avatar():
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as c:
            _asegurar_perfil_avatar(c)
            c.execute("""SELECT id_usuario,edad,estilo,cuerpo,rostro,cabello,estetica,
                         foto_analizada,avatar_dna,fecha_actualizacion
                         FROM avatar_perfiles WHERE id_usuario=%s""", (g.id_usuario,))
            perfil = c.fetchone()
            if not perfil:
                return jsonify({"usuario_id":g.id_usuario,"perfil":None}),200
            return jsonify({"usuario_id":g.id_usuario,"perfil":perfil}),200
    finally:
        conn.close()

@avatar_bp.route("/avatar/perfil", methods=["PUT"])
@requiere_autenticacion
def guardar_perfil_avatar():
    data = request.get_json(silent=True) or {}
    permitido = ("edad","estilo","cuerpo","rostro","cabello","estetica","foto_analizada","avatar_dna")
    cambios = {k:data[k] for k in permitido if k in data}

    if "edad" in cambios:
        try:
            cambios["edad"] = int(cambios["edad"])
        except (TypeError,ValueError):
            return jsonify({"error":"La edad debe ser numérica."}),400
        if not 0 <= cambios["edad"] <= 100:
            return jsonify({"error":"La edad debe estar entre 0 y 100 años."}),400
    if "estilo" in cambios:
        cambios["estilo"] = str(cambios["estilo"]).strip()[:50]
    if "foto_analizada" in cambios:
        cambios["foto_analizada"] = bool(cambios["foto_analizada"])

    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_perfil_avatar(c)
            c.execute("SELECT id_avatar FROM avatar_perfiles WHERE id_usuario=%s",(g.id_usuario,))
            existe=c.fetchone()
            if existe:
                if not cambios:return jsonify({"success":True,"mensaje":"No había cambios que guardar."}),200
                sets=[]; vals=[]
                for key,value in cambios.items():
                    sets.append(key+"=%s")
                    vals.append(json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value)
                vals.append(g.id_usuario)
                c.execute("UPDATE avatar_perfiles SET "+",".join(sets)+" WHERE id_usuario=%s",vals)
            else:
                columnas=["id_usuario"]+list(cambios.keys())
                valores=[g.id_usuario]+[json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for v in cambios.values()]
                c.execute("INSERT INTO avatar_perfiles ("+",".join(columnas)+") VALUES ("+(",".join(["%s"]*len(columnas))+")"),valores)
        conn.commit()
        return jsonify({"success":True,"mensaje":"Perfil del avatar guardado correctamente."}),200
    except Exception:
        conn.rollback()
        return jsonify({"error":"No se pudo guardar el perfil del avatar."}),500
    finally:
        conn.close()

@avatar_bp.route(
    "/avatar/render",
    methods=["POST"]
)
def render_avatar():

    imagen_guardada_path = None

    try:

        # =============================================
        # IMAGEN
        # =============================================

        archivo = request.files.get(
            "imagen"
        )

        if not archivo:

            return jsonify({
                "status": "error",
                "error": "Primero debes subir una imagen."
            }), 400

        if not allowed_file(
            archivo.filename
        ):

            return jsonify({
                "status": "error",
                "error": "Formato de imagen no permitido."
            }), 400

        # =============================================
        # TAMAÑO Y CONTENIDO REAL DE LA IMAGEN
        # =============================================
        imagen_bytes = archivo.read(Config.MAX_CONTENT_LENGTH + 1)
        if len(imagen_bytes) > Config.MAX_CONTENT_LENGTH:
            return jsonify({"status":"error","error":"La imagen supera el límite permitido."}), 400
        if not imagen_bytes or cv2.imdecode(np.frombuffer(imagen_bytes, dtype=np.uint8), cv2.IMREAD_COLOR) is None:
            return jsonify({"status":"error","error":"El archivo no contiene una imagen válida."}), 400

        # =============================================
        # ALTURA
        # =============================================

        altura = request.form.get(
            "altura",
            170,
            type=float
        )

        edad = request.form.get(
            "edad",
            25,
            type=float
        )

        if altura < 100 or altura > 250:

            return jsonify({
                "status": "error",
                "error": "La altura debe estar entre 100 y 250 cm."
            }), 400

        if edad < 0 or edad > 100:
            return jsonify({
                "status": "error",
                "error": "La edad debe estar entre 0 y 100 años."
            }), 400

        # =============================================
        # ESTILO
        # =============================================

        estilo = request.form.get(
            "estilo",
            "casual"
        ).lower()

        # =============================================
        # GUARDAR IMAGEN
        # =============================================

        clave_cache = cache.hacer_clave(
            "avatar-render-v3-photo-texture", imagen_bytes, altura, edad, estilo
        )

        resultado_cacheado = cache.obtener(clave_cache)

        if resultado_cacheado is not None:
            respuesta_cache = dict(resultado_cacheado)
            respuesta_cache["cache"] = True
            return jsonify(respuesta_cache), 200

        upload_folder = Config.UPLOAD_FOLDER

        os.makedirs(
            upload_folder,
            exist_ok=True
        )

        extension = archivo.filename.rsplit(
            ".",
            1
        )[1].lower()

        nombre_archivo = (
            f"avatar_{uuid.uuid4().hex}.{extension}"
        )

        imagen_guardada_path = os.path.join(
            upload_folder,
            nombre_archivo
        )

        with open(imagen_guardada_path, "wb") as f:
            f.write(imagen_bytes)

        print(
            f"[FITAI] Imagen guardada: "
            f"{imagen_guardada_path}"
        )

        # =============================================
        # MEDIAPIPE REAL
        # =============================================

        print(
            "[FITAI] Ejecutando MediaPipe Pose..."
        )

        deteccion = analizar_medidas(
            imagen_guardada_path,
            altura
        )

        if not deteccion.get(
            "detectado",
            False
        ):

            return jsonify({
                "status": "error",
                "error": deteccion.get(
                    "mensaje",
                    "No se pudo detectar el cuerpo completo."
                )
            }), 422

        # =============================================
        # RECOMENDADOR
        # =============================================

        recomendacion = generar_recomendacion(
            altura=altura,
            tipo_cuerpo=None,
            estilo_preferido=estilo
        )

        # =============================================
        # AVATAR DNA
        # =============================================
        proporciones = deteccion.get("proporciones", {})
        avatar_medidas = deteccion.get("avatar", {})
        hombros_ref = max(float(proporciones.get("hombros", 0.5)), 0.001)
        cadera_ref = max(float(proporciones.get("cadera", 0.5)), 0.001)
        torso_ref = max(float(avatar_medidas.get("escala_torso", 0.5)), 0.001)

        avatar_dna = build_avatar_dna(
            age=edad,
            height_cm=altura,
            body={
                "shoulder": max(0.0, min(1.0, hombros_ref / 0.34)),
                "waist": max(0.0, min(1.0, cadera_ref / 0.30)),
                "body_ratio": max(0.0, min(1.0, torso_ref / 0.18)),
                "muscle": 0.50,
                "body_fat": 0.50,
            },
            face=deteccion.get("identidad_facial", {}),
        )

        # El frontend y backend deben consumir exactamente el mismo modelo base.
        avatar_dna["render"]["model_url"] = Config.AVATAR_MODEL_URL

        # =============================================
        # RESPUESTA
        # =============================================

        respuesta = {

            "status": "success",

            "mensaje": (
                "Análisis corporal y ajuste del avatar "
                "completado exitosamente."
            ),

            # MediaPipe
            "deteccion_corporal": deteccion.get(
                "precision",
                0
            ),

            "puntos_mapeados": deteccion.get(
                "puntos_mapeados",
                {}
            ),

            "altura_cm": deteccion.get(
                "altura_cm",
                altura
            ),

            "medidas": deteccion.get(
                "medidas_estimadas",
                {}
            ),

            "proporciones": deteccion.get(
                "proporciones",
                {}
            ),

            "avatar_dna": avatar_dna,

            "avatar": deteccion.get(
                "avatar",
                {}
            ),

            # Recomendador
            "ajuste_prenda": recomendacion.get(
                "ajuste",
                0
            ),

            "recomendacion_score": recomendacion.get(
                "recomendacion_score",
                0
            ),

            "outfit_titulo": recomendacion.get(
                "nombre",
                "Outfit recomendado"
            ),

            "outfit_descripcion": recomendacion.get(
                "descripcion",
                ""
            )
        }

        print(
            "[FITAI] Análisis completado correctamente."
        )

        cache.guardar(clave_cache, respuesta, ttl_segundos=600)

        return jsonify(
            respuesta
        ), 200

    except Exception as error:

        print(
            "[FITAI] ERROR EN AVATAR:",
            error
        )

        return jsonify({

            "status": "error",

            "error": (
                "Ocurrió un error procesando "
                "la imagen."
            ),

        }), 500

    finally:
        # La foto ya cumplió su propósito (medir el cuerpo); no hace
        # falta conservarla en el servidor indefinidamente.
        if imagen_guardada_path and os.path.exists(imagen_guardada_path):
            try:
                os.remove(imagen_guardada_path)
            except OSError:
                pass