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

CATEGORIAS = {
    "camisa": "camisa", "camisas": "camisa", "camiseta": "camisa", "camisetas": "camisa",
    "parte superior": "camisa", "top": "camisa",
    "pantalon": "pantalon", "pantalones": "pantalon", "jean": "pantalon", "jeans": "pantalon",
    "accesorio": "accesorio", "accesorios": "accesorio",
}

def _asegurar_catalogo(cursor):
    """Si la tabla existe pero está vacía, crea el catálogo inicial una sola vez."""
    cursor.execute("SELECT COUNT(*) AS total FROM prendas WHERE id_usuario IS NULL")
    total = int((cursor.fetchone() or {}).get("total", 0))
    if total:
        return

    cursor.executemany(
        """INSERT INTO prendas
           (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
           VALUES (NULL,%s,%s,%s,%s,%s,%s,%s,%s)""",
        CATALOGO_INICIAL
    )


def _categoria_normalizada(valor):
    texto = str(valor or "").strip().lower()
    return CATEGORIAS.get(texto, texto)

def _es_categoria(prenda, categoria):
    if not categoria:
        return True
    objetivo = _categoria_normalizada(categoria)
    actual = _categoria_normalizada(prenda.get("categoria"))
    if objetivo == actual:
        return True
    texto = " ".join(str(prenda.get(k) or "").lower() for k in ("nombre_prenda", "categoria"))
    if objetivo == "camisa":
        return any(x in texto for x in ("camisa", "camiseta", "blusa", "chaqueta", "blazer", "sudadera"))
    if objetivo == "pantalon":
        return any(x in texto for x in ("pantalón", "pantalon", "jean", "jogger", "short", "falda"))
    if objetivo == "accesorio":
        return any(x in texto for x in ("reloj", "gorra", "gafas", "cintur", "bolso", "mochila", "collar", "pulsera", "zapato"))
    return False

def _row(r, es_propia=False):
    return {
        "id": r["id_prenda"],
        "id_prenda": r["id_prenda"],
        "nombre": r["nombre_prenda"],
        "nombre_prenda": r["nombre_prenda"],
        "categoria": r["categoria"],
        "color": r["color"],
        "talla": r["talla"],
        "estilo": r["estilo"],
        "temporada": r["temporada"],
        "url_imagen": r["url_imagen"],
        "precio": float(r["precio"]) if r.get("precio") is not None else None,
        "es_propia": bool(es_propia),
        "disponible_para_compra": not bool(es_propia),
        "origen": "mi_armario" if es_propia else "catalogo",
    }

def _obtener_catalogo(categoria=None, estilo=None, limite=100):
    conn = obtener_conexion()
    if not conn:
        raise RuntimeError("Base de datos no disponible.")
    try:
        with conn.cursor() as cursor:
            _asegurar_catalogo(cursor)
            conn.commit()
            cursor.execute("""SELECT id_prenda,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio
                              FROM prendas WHERE id_usuario IS NULL ORDER BY id_prenda""")
            filas = cursor.fetchall()
            resultado = []
            for fila in filas:
                if categoria and not _es_categoria(fila, categoria):
                    continue
                if estilo and str(fila.get("estilo") or "").lower() != str(estilo).strip().lower():
                    continue
                resultado.append(_row(fila, False))
                if len(resultado) >= limite:
                    break
            return resultado
    finally:
        conn.close()

@ropa_bp.route("/ropa", methods=["GET"])
def obtener_ropa():
    categoria = request.args.get("categoria")
    estilo = request.args.get("estilo")
    try:
        limite = max(1, min(int(request.args.get("limite", 100)), 200))
    except (TypeError, ValueError):
        return jsonify({"error": "El límite debe ser un número entre 1 y 200."}), 400

    try:
        return jsonify(_obtener_catalogo(categoria, estilo, limite)), 200
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503

@ropa_bp.route("/mis-prendas", methods=["GET"])
@requiere_autenticacion
def mis_prendas():
    categoria = request.args.get("categoria")
    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT id_prenda,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio
                              FROM prendas WHERE id_usuario=%s ORDER BY fecha_subida DESC, id_prenda DESC""",
                           (g.id_usuario,))
            resultado = [_row(r, True) for r in cursor.fetchall()]
            if categoria:
                resultado = [r for r in resultado if _es_categoria(r, categoria)]
            return jsonify(resultado), 200
    finally:
        conn.close()

@ropa_bp.route("/vestuario", methods=["GET"])
@requiere_autenticacion
def vestuario():
    """Devuelve en una sola respuesta el armario del usuario y el catálogo."""
    categoria = request.args.get("categoria")
    estilo = request.args.get("estilo")

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("""SELECT id_prenda,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio
                              FROM prendas WHERE id_usuario=%s ORDER BY fecha_subida DESC, id_prenda DESC""",
                           (g.id_usuario,))
            propias = [_row(r, True) for r in cursor.fetchall()]

        propias = [r for r in propias if (not categoria or _es_categoria(r, categoria))]
        if estilo:
            propias = [r for r in propias if str(r.get("estilo") or "").lower() == estilo.strip().lower()]

        catalogo = _obtener_catalogo(categoria, estilo, 200)
        return jsonify({
            "usuario_id": g.id_usuario,
            "mi_armario": propias,
            "catalogo": catalogo,
            "total_armario": len(propias),
            "total_catalogo": len(catalogo)
        }), 200
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    finally:
        conn.close()

@ropa_bp.route("/ropa", methods=["POST"])
@requiere_autenticacion
def crear_prenda():
    data = request.get_json(silent=True) or {}
    nombre = str(data.get("nombre", "")).strip()
    if not nombre or len(nombre) > 100:
        return jsonify({"error": "El nombre de la prenda es obligatorio y debe tener máximo 100 caracteres."}), 400

    categoria = str(data.get("categoria", "")).strip()[:50] or "otro"
    color = str(data.get("color", "")).strip()[:50] or None
    talla = str(data.get("talla", "")).strip()[:20] or None
    estilo = str(data.get("estilo", "")).strip()[:50] or "casual"
    temporada = str(data.get("temporada", "")).strip()[:30] or "todo"
    url_imagen = str(data.get("url_imagen", "")).strip()[:500] or None

    precio = data.get("precio")
    if precio in ("", None):
        precio = None
    else:
        try:
            precio = float(precio)
            if precio < 0 or precio > 1000000:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "El precio debe ser un número entre 0 y 1.000.000."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute("""INSERT INTO prendas
                (id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (g.id_usuario, nombre, categoria, color, talla, estilo, temporada, url_imagen, precio))
            conn.commit()
            return jsonify({
                "success": True,
                "id_prenda": cursor.lastrowid,
                "es_propia": True,
                "origen": "mi_armario",
                "disponible_para_compra": False
            }), 201
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo guardar la prenda."}), 500
    finally:
        conn.close()

@ropa_bp.route("/ropa/<int:id_prenda>", methods=["PUT"])
@requiere_autenticacion
def actualizar_prenda(id_prenda):
    data = request.get_json(silent=True) or {}
    campos = {
        "nombre_prenda": str(data.get("nombre", "")).strip()[:100] if "nombre" in data else None,
        "categoria": str(data.get("categoria", "")).strip()[:50] if "categoria" in data else None,
        "color": str(data.get("color", "")).strip()[:50] if "color" in data else None,
        "talla": str(data.get("talla", "")).strip()[:20] if "talla" in data else None,
        "estilo": str(data.get("estilo", "")).strip()[:50] if "estilo" in data else None,
        "temporada": str(data.get("temporada", "")).strip()[:30] if "temporada" in data else None,
        "url_imagen": str(data.get("url_imagen", "")).strip()[:500] if "url_imagen" in data else None,
    }
    precio = data.get("precio") if "precio" in data else None
    if "precio" in data:
        try:
            precio = None if precio in ("", None) else float(precio)
            if precio is not None and (precio < 0 or precio > 1000000):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "El precio no es válido."}), 400

    cambios = []
    valores = []
    for columna, valor in campos.items():
        if valor is not None:
            if columna == "nombre_prenda" and not valor:
                return jsonify({"error": "El nombre no puede quedar vacío."}), 400
            cambios.append(f"{columna}=%s")
            valores.append(valor)
    if "precio" in data:
        cambios.append("precio=%s")
        valores.append(precio)
    if not cambios:
        return jsonify({"error": "No hay campos para actualizar."}), 400

    conn = obtener_conexion()
    if not conn:
        return jsonify({"error": "Base de datos no disponible."}), 503
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"UPDATE prendas SET {', '.join(cambios)} WHERE id_prenda=%s AND id_usuario=%s",
                [*valores, id_prenda]
            )
            if cursor.rowcount == 0:
                return jsonify({"error": "Prenda no encontrada en tu armario."}), 404
            conn.commit()
            return jsonify({"success": True, "id_prenda": id_prenda, "es_propia": True}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo actualizar la prenda."}), 500
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
                return jsonify({"error": "Prenda no encontrada en tu armario."}), 404
            conn.commit()
            return jsonify({"success": True}), 200
    except Exception:
        conn.rollback()
        return jsonify({"error": "No se pudo eliminar la prenda."}), 500
    finally:
        conn.close()
