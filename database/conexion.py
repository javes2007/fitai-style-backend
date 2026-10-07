import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from backend.config import Config

# Pool de conexiones: se crea una única vez y se reutiliza en cada
# petición, en vez de abrir/cerrar una conexión TCP nueva a MySQL por
# cada consulta (mucho más rápido y evita agotar conexiones bajo carga).
_pool = None


def _crear_pool():
    return PooledDB(
        creator=pymysql,
        maxconnections=10,   # máximo de conexiones abiertas a la vez
        mincached=1,         # conexiones inactivas mantenidas listas
        maxcached=5,
        blocking=True,       # espera si el pool está lleno, en vez de fallar
        ping=1,              # verifica la conexión antes de entregarla (evita
                              # el clásico error "MySQL server has gone away")
        host=Config.DB_HOST,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        port=Config.DB_PORT,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def obtener_conexion():
    """Retorna una conexión del pool a la base de datos MySQL.

    El objeto devuelto se comporta igual que una conexión normal de
    PyMySQL (cursor(), commit(), close()...), pero al llamar a close()
    la conexión vuelve al pool para ser reutilizada en vez de cerrarse
    de verdad. Los cursores devuelven cada fila como diccionario
    (ej. usuario["email"]).
    """
    global _pool
    try:
        if _pool is None:
            _pool = _crear_pool()
        return _pool.connection()
    except Exception as e:
        print(f"Error al conectar con la base de datos MySQL: {e}")
        return None
