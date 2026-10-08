from flask import Blueprint, jsonify, request, g
from backend.auth.tokens import requiere_autenticacion
from backend.database.conexion import obtener_conexion

compras_bp = Blueprint("compras", __name__)

def _asegurar_tablas(c):
    c.execute("""CREATE TABLE IF NOT EXISTS carrito (
        id_carrito INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL, id_prenda INT NOT NULL, cantidad INT NOT NULL DEFAULT 1,
        fecha_agregado TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_carrito_usuario_prenda (id_usuario,id_prenda),
        INDEX idx_carrito_usuario (id_usuario)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS pedidos (
        id_pedido INT AUTO_INCREMENT PRIMARY KEY,
        id_usuario INT NOT NULL, total DECIMAL(12,2) NOT NULL DEFAULT 0,
        estado VARCHAR(30) NOT NULL DEFAULT 'pendiente',
        fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_pedidos_usuario (id_usuario)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    c.execute("""CREATE TABLE IF NOT EXISTS pedido_detalles (
        id_detalle INT AUTO_INCREMENT PRIMARY KEY, id_pedido INT NOT NULL,
        id_prenda_catalogo INT NOT NULL, nombre_prenda VARCHAR(100) NOT NULL,
        precio DECIMAL(12,2) NOT NULL, cantidad INT NOT NULL DEFAULT 1,
        INDEX idx_detalle_pedido (id_pedido)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

def _item(r):
    return {"id_prenda":r["id_prenda"],"nombre":r["nombre_prenda"],"categoria":r["categoria"],
            "color":r["color"],"talla":r["talla"],"estilo":r["estilo"],
            "url_imagen":r["url_imagen"],"precio":float(r["precio"] or 0),
            "cantidad":int(r.get("cantidad",1))}

@compras_bp.route("/carrito", methods=["GET"])
@requiere_autenticacion
def carrito():
    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            c.execute("""SELECT p.id_prenda,p.nombre_prenda,p.categoria,p.color,p.talla,p.estilo,
                         p.url_imagen,p.precio,ca.cantidad FROM carrito ca JOIN prendas p
                         ON p.id_prenda=ca.id_prenda WHERE ca.id_usuario=%s AND p.id_usuario IS NULL
                         ORDER BY ca.fecha_agregado DESC""",(g.id_usuario,))
            items=[_item(x) for x in c.fetchall()]
            return jsonify({"items":items,"total":round(sum(x["precio"]*x["cantidad"] for x in items),2),
                            "cantidad":sum(x["cantidad"] for x in items)}),200
    finally: conn.close()

@compras_bp.route("/carrito", methods=["POST"])
@requiere_autenticacion
def agregar():
    data=request.get_json(silent=True) or {}
    try: pid=int(data.get("id_prenda")); cantidad=max(1,min(int(data.get("cantidad",1)),20))
    except (TypeError,ValueError): return jsonify({"error":"id_prenda y cantidad no son válidos."}),400
    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            c.execute("SELECT * FROM prendas WHERE id_prenda=%s",(pid,)); p=c.fetchone()
            if not p:return jsonify({"error":"Prenda no encontrada."}),404
            if p["id_usuario"] is not None:return jsonify({"error":"La prenda ya pertenece a tu armario."}),409
            if not p["precio"] or float(p["precio"])<=0:return jsonify({"error":"La prenda no tiene precio válido."}),409
            c.execute("""INSERT INTO carrito(id_usuario,id_prenda,cantidad) VALUES(%s,%s,%s)
                         ON DUPLICATE KEY UPDATE cantidad=LEAST(cantidad+VALUES(cantidad),20)""",
                      (g.id_usuario,pid,cantidad))
        conn.commit(); return jsonify({"success":True,"mensaje":"Prenda añadida al carrito."}),201
    except Exception:
        conn.rollback(); return jsonify({"error":"No se pudo añadir la prenda al carrito."}),500
    finally: conn.close()

@compras_bp.route("/carrito/<int:id_prenda>", methods=["DELETE"])
@requiere_autenticacion
def quitar(id_prenda):
    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c); c.execute("DELETE FROM carrito WHERE id_usuario=%s AND id_prenda=%s",(g.id_usuario,id_prenda))
            if not c.rowcount:return jsonify({"error":"La prenda no está en tu carrito."}),404
        conn.commit(); return jsonify({"success":True}),200
    except Exception:
        conn.rollback(); return jsonify({"error":"No se pudo actualizar el carrito."}),500
    finally: conn.close()

@compras_bp.route("/compras", methods=["POST"])
@requiere_autenticacion
def comprar():
    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            c.execute("""SELECT p.* ,ca.cantidad FROM carrito ca JOIN prendas p ON p.id_prenda=ca.id_prenda
                         WHERE ca.id_usuario=%s AND p.id_usuario IS NULL FOR UPDATE""",(g.id_usuario,))
            items=c.fetchall()
            if not items:return jsonify({"error":"Tu carrito está vacío."}),400
            total=sum(float(x["precio"] or 0)*int(x["cantidad"]) for x in items)
            c.execute("INSERT INTO pedidos(id_usuario,total,estado) VALUES(%s,%s,'pendiente')",(g.id_usuario,total))
            oid=c.lastrowid
            for x in items:
                c.execute("""INSERT INTO pedido_detalles(id_pedido,id_prenda_catalogo,nombre_prenda,precio,cantidad)
                             VALUES(%s,%s,%s,%s,%s)""",(oid,x["id_prenda"],x["nombre_prenda"],x["precio"],x["cantidad"]))
                for _ in range(int(x["cantidad"])):
                    c.execute("""INSERT INTO prendas(id_usuario,nombre_prenda,categoria,color,talla,estilo,temporada,url_imagen,precio)
                                 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                              (g.id_usuario,x["nombre_prenda"],x["categoria"],x["color"],x["talla"],x["estilo"],
                               x["temporada"],x["url_imagen"],x["precio"]))
            c.execute("DELETE FROM carrito WHERE id_usuario=%s",(g.id_usuario,))
        conn.commit()
        return jsonify({"success":True,"id_pedido":oid,"estado":"pendiente","total":round(total,2),
                        "mensaje":"Compra registrada y prendas añadidas a tu armario."}),201
    except Exception:
        conn.rollback(); return jsonify({"error":"No se pudo finalizar la compra."}),500
    finally: conn.close()

@compras_bp.route("/compras", methods=["GET"])
@requiere_autenticacion
def compras():
    conn=obtener_conexion()
    if not conn:return jsonify({"error":"Base de datos no disponible."}),503
    try:
        with conn.cursor() as c:
            _asegurar_tablas(c)
            c.execute("SELECT id_pedido,total,estado,fecha_creacion FROM pedidos WHERE id_usuario=%s ORDER BY fecha_creacion DESC",(g.id_usuario,))
            pedidos=c.fetchall()
            for p in pedidos:
                p["total"]=float(p["total"])
                c.execute("SELECT id_detalle,id_prenda_catalogo,nombre_prenda,precio,cantidad FROM pedido_detalles WHERE id_pedido=%s",(p["id_pedido"],))
                p["detalles"]=c.fetchall()
            return jsonify(pedidos),200
    finally: conn.close()
