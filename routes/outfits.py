from flask import Blueprint, jsonify, request, g
from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion

outfits_bp = Blueprint("outfits", __name__)

@outfits_bp.route("/outfits", methods=["GET"])
@requiere_autenticacion
def listar_outfits():
    conn = obtener_conexion()
    if not conn: return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            c.execute("""SELECT id_outfit,nombre,creado_por,fecha_creacion
                         FROM outfits WHERE id_usuario=%s ORDER BY fecha_creacion DESC""",(g.id_usuario,))
            outfits=c.fetchall()
            for o in outfits:
                c.execute("""SELECT p.id_prenda,p.nombre_prenda,p.categoria,p.color,p.talla,p.estilo,p.url_imagen,p.precio
                             FROM outfit_prendas op JOIN prendas p ON p.id_prenda=op.id_prenda
                             WHERE op.id_outfit=%s AND p.id_usuario=%s""",(o["id_outfit"],g.id_usuario))
                o["prendas"]=c.fetchall()
            return jsonify(outfits),200
    finally: conn.close()

@outfits_bp.route("/outfits", methods=["POST"])
@requiere_autenticacion
def crear_outfit():
    data=request.get_json(silent=True) or {}
    nombre=str(data.get("nombre","")).strip()
    ids=data.get("prendas",[])
    if not nombre or len(nombre)>100 or not isinstance(ids,list) or len(ids)>30:
        return jsonify({"error":"Nombre o lista de prendas no válidos."}),400
    try: ids=[int(x) for x in ids]
    except (TypeError,ValueError): return jsonify({"error":"Las prendas deben ser IDs numéricos."}),400

    conn=obtener_conexion()
    if not conn: return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            if ids:
                marks=",".join(["%s"]*len(ids))
                c.execute(f"SELECT id_prenda FROM prendas WHERE id_usuario=%s AND id_prenda IN ({marks})",[g.id_usuario,*ids])
                valid={r["id_prenda"] for r in c.fetchall()}
                if valid != set(ids):
                    return jsonify({"error":"Una o más prendas no pertenecen a tu cuenta."}),403
            c.execute("INSERT INTO outfits (id_usuario,nombre,creado_por) VALUES (%s,%s,'usuario')",(g.id_usuario,nombre))
            oid=c.lastrowid
            for pid in dict.fromkeys(ids):
                c.execute("INSERT INTO outfit_prendas (id_outfit,id_prenda) VALUES (%s,%s)",(oid,pid))
        conn.commit()
        return jsonify({"success":True,"id_outfit":oid}),201
    except Exception:
        conn.rollback()
        return jsonify({"error":"No se pudo crear el outfit."}),500
    finally: conn.close()

@outfits_bp.route("/outfits/<int:id_outfit>", methods=["DELETE"])
@requiere_autenticacion
def eliminar_outfit(id_outfit):
    conn=obtener_conexion()
    if not conn: return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            c.execute("DELETE FROM outfits WHERE id_outfit=%s AND id_usuario=%s",(id_outfit,g.id_usuario))
            if not c.rowcount: return jsonify({"error":"Outfit no encontrado."}),404
        conn.commit()
        return jsonify({"success":True}),200
    except Exception:
        conn.rollback()
        return jsonify({"error":"No se pudo eliminar el outfit."}),500
    finally: conn.close()
