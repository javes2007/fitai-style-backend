from flask import Blueprint, jsonify, request, g
from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion

ropa_bp = Blueprint("ropa", __name__)

# Catálogo público inicial. El SQL lo siembra en `prendas` con id_usuario NULL.
CATALOGO_INICIAL = [
    ("Camiseta Básica Pima", "Casual", "Blanco", "M", "casual", "todo", "img/ava.jpg", 25.00),
    ("Jeans Slim Fit", "Casual", "Azul Oscuro", "32", "casual", "todo", "img/avaratare.jpg", 45.00),
    ("Chaqueta Denim Vintage", "Casual", "Celeste", "L", "casual", "todo", "img/avat.jpg", 60.00),
    ("Blazer Formal Fit", "Formal", "Negro", "M", "formal", "todo", "img/avata.jpg", 85.00),
    ("Camisa Oxford Premium", "Formal", "Azul Claro", "S", "formal", "todo", "img/avatar.jpg", 35.00),
    ("Pantalón de Vestir Sastre", "Formal", "Gris Oxford", "30", "formal", "todo", "img/modelo.jpg", 50.00),
    ("Jogger Deportivo Tech", "Deportivo", "Gris Melange", "M", "deportivo", "todo", "img/ava.jpg", 30.00),
    ("Camiseta Deportiva Transpirable", "Deportivo", "Negro", "L", "deportivo", "todo", "img/avaratare.jpg", 20.00),
    ("Rompevientos Ligero", "Deportivo", "Verde Oliva", "XL", "deportivo", "todo", "img/avat.jpg", 55.00),
]

def _row(r):
    return {
        "id": r["id_prenda"], "nombre": r["nombre_prenda"], "categoria": r["categoria"],
        "color": r["color"], "talla": r["talla"], "estilo": r["estilo"],
        "temporada": r["temporada"], "url_imagen": r["url_imagen"], "precio": float(r["precio"]) if r.get("precio") is not None else None
    }

@ropa_bp.route("/ropa", methods=["GET"])
def obtener_ropa():
    categoria = request.args.get("categoria")
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            sql = """SELECT id_prenda,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio
                     FROM prendas WHERE id_usuario IS NULL"""
            params = []
            if categoria:
                sql += " AND LOWER(categoria)=LOWER(%s)"
                params.append(categoria)
            sql += " ORDER BY id_prenda"
            cursor.execute(sql, params)
            return jsonify([_row(r) for r in cursor.fetchall()]), 200
    finally:
        conn.close()

@ropa_bp.route("/mis-prendas", methods=["GET"])
@requiere_autenticacion
def mis_prendas():
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT id_prenda,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio
                              FROM prendas WHERE id_usuario=%s ORDER BY fecha_subida DESC""", (g.id_usuario,))
            return jsonify([_row(r) for r in cursor.fetchall()]), 200
    finally:
        conn.close()

@ropa_bp.route("/ropa", methods=["POST"])
@requiere_autenticacion
def crear_prenda():
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre", "")).strip()
    if not nombre or len(nombre) > 100:
        return jsonify({"error": "El nombre de la prenda es obligatorio y debe tener máximo 100 caracteres."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO prendas
                (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (g.id_usuario, nombre, data.get("categoria"), data.get("color"), data.get("talla"),
                 data.get("estilo"), data.get("temporada"), data.get("url_imagen"), data.get("precio")))
            conn.commit()
            return jsonify({"success": True, "id_prenda": cursor.lastrowid}), 201
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo guardar la prenda."}), 500
    finally:
        conn.close()

@ropa_bp.route("/ropa/<int:id_prenda>", methods=["DELETE"])
@requiere_autenticacion
def eliminar_prenda(id_prenda):
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM prendas WHERE id_prenda=%s AND id_usuario=%s", (id_prenda, g.id_usuario))
            if cursor.rowcount == 0:
                return jsonify({"error": "Prenda no encontrada."}), 404
            conn.commit()
            return jsonify({"success": True}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo eliminar la prenda."}), 500
    finally:
        conn.close()
