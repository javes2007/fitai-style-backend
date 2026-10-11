"""Caché TTL acotada para resultados costosos de IA y visión por computador.

La caché vive en memoria del proceso y se pierde al reiniciar. Tiene un límite
de entradas para impedir crecimiento ilimitado bajo tráfico variado.
"""
from collections import OrderedDict
import hashlib
import threading
import time

_MAX_ENTRADAS = 256
_cache = OrderedDict()
_lock = threading.RLock()


def hacer_clave(*partes):
    """Crea una clave SHA-256 estable para texto, parámetros o bytes."""
    h = hashlib.sha256()
    for parte in partes:
        if isinstance(parte, (bytes, bytearray, memoryview)):
            h.update(bytes(parte))
        else:
            h.update(str(parte).encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()


def _limpiar_expiradas(ahora):
    expiradas = [clave for clave, (_, expira_en) in _cache.items() if expira_en <= ahora]
    for clave in expiradas:
        _cache.pop(clave, None)


def obtener(clave):
    """Devuelve un resultado vigente o None si no existe/expiró."""
    ahora = time.monotonic()
    with _lock:
        entrada = _cache.get(clave)
        if entrada is None:
            return None
        valor, expira_en = entrada
        if expira_en <= ahora:
            _cache.pop(clave, None)
            return None
        _cache.move_to_end(clave)
        return valor


def guardar(clave, valor, ttl_segundos=600):
    """Guarda un resultado con TTL y elimina entradas antiguas si hace falta."""
    try:
        ttl = max(0, float(ttl_segundos))
    except (TypeError, ValueError):
        ttl = 600
    if ttl == 0:
        return
    ahora = time.monotonic()
    with _lock:
        _limpiar_expiradas(ahora)
        _cache[clave] = (valor, ahora + ttl)
        _cache.move_to_end(clave)
        while len(_cache) > _MAX_ENTRADAS:
            _cache.popitem(last=False)


def limpiar():
    """Vacía la caché (útil en pruebas y mantenimiento)."""
    with _lock:
        _cache.clear()


def estado():
    """Devuelve métricas básicas sin exponer claves ni contenido cacheado."""
    ahora = time.monotonic()
    with _lock:
        _limpiar_expiradas(ahora)
        return {"entradas": len(_cache), "max_entradas": _MAX_ENTRADAS}
