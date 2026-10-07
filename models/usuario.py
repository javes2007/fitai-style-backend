from backend.database.conexion import obtener_conexion
from werkzeug.security import generate_password_hash, check_password_hash

class Usuario:
    @staticmethod
    def crear(nombre, email, contrasena):
        conn = obtener_conexion()
        if not conn:
            raise RuntimeError("Base de datos no disponible.")
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO usuarios (nombre, email, contrasena) VALUES (%s, %s, %s)",
                    (nombre, email, generate_password_hash(contrasena))
                )
                conn.commit()
                return cursor.lastrowid
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def obtener_por_email(email):
        conn = obtener_conexion()
        if not conn:
            raise RuntimeError("Base de datos no disponible.")
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM usuarios WHERE email = %s", (email,))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def obtener_por_id(id_usuario):
        conn = obtener_conexion()
        if not conn:
            raise RuntimeError("Base de datos no disponible.")
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM usuarios WHERE id_usuario = %s", (id_usuario,))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def actualizar_medidas(id_usuario, altura, ancho_hombros, pecho, cintura, cadera):
        conn = obtener_conexion()
        if not conn:
            return False
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """UPDATE usuarios
                       SET altura=%s, ancho_hombros=%s, pecho=%s, cintura=%s, cadera=%s
                       WHERE id_usuario=%s""",
                    (altura, ancho_hombros, pecho, cintura, cadera, id_usuario)
                )
                conn.commit()
                return cursor.rowcount == 1
        except Exception:
            conn.rollback()
            return False
        finally:
            conn.close()

    @staticmethod
    def verificar_contrasena(hash_guardado, contrasena):
        return check_password_hash(hash_guardado, contrasena)
