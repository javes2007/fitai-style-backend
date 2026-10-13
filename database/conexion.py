import hashlib
import logging
import os
import threading
import time

import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from backend.config import Config

_pool = None
_pool_lock = threading.Lock()
_logger = logging.getLogger("fitai.database")


class MonitoredDictCursor(pymysql.cursors.DictCursor):
    """Registra consultas lentas sin imprimir SQL, parámetros ni datos personales."""

    def execute(self, query, args=None):
        started = time.perf_counter()
        try:
            return super().execute(query, args)
        finally:
            elapsed = time.perf_counter() - started
            if elapsed >= Config.DB_SLOW_QUERY_SECONDS:
                fingerprint = hashlib.sha256(str(query).encode("utf-8", "replace")).hexdigest()[:12]
                _logger.warning("Consulta MySQL lenta: duration_seconds=%.3f fingerprint=%s", elapsed, fingerprint)


def _crear_pool():
    """Crea un pool acotado con timeouts y TLS verificado por CA si se configura."""
    parametros = {
        "creator": pymysql,
        "maxconnections": 10,
        "mincached": 0,
        "maxcached": 5,
        "maxusage": 500,
        "blocking": False,
        "ping": 1,
        "host": Config.DB_HOST,
        "user": Config.DB_USER,
        "password": Config.DB_PASSWORD,
        "database": Config.DB_NAME,
        "port": Config.DB_PORT,
        "charset": "utf8mb4",
        "cursorclass": MonitoredDictCursor,
        "autocommit": False,
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
    }
    if Config.DB_SSL_CA:
        parametros["ssl"] = {"ca": Config.DB_SSL_CA}
    return PooledDB(**parametros)


def obtener_conexion():
    """Obtiene una conexión reutilizable; devuelve None si no está disponible."""
    global _pool
    try:
        if _pool is None:
            with _pool_lock:
                if _pool is None:
                    _pool = _crear_pool()
        return _pool.connection()
    except Exception as exc:
        # No imprimir credenciales ni parámetros de conexión.
        _logger.warning("No se pudo obtener una conexión MySQL (%s).", type(exc).__name__)
        return None
