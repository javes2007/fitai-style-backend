"""
Caché simple en memoria con tiempo de vida (TTL).

Pensada para evitar llamadas repetidas y costosas (Gemini, MediaPipe)
cuando llega exactamente la misma imagen con los mismos parámetros.

Limitaciones honestas:
- Vive solo en memoria del proceso: se pierde al reiniciar el servidor.
- Si el servidor corre con varios procesos/workers (p. ej. gunicorn con
  -w 4), cada proceso tiene su propia caché independiente.
Para un proyecto de este tamaño es suficiente y no añade dependencias
nuevas (usa solo la librería estándar de Python).
"""

import time
import hashlib
import threading

_cache = {}
_lock = threading.Lock()


def hacer_clave(*partes):
    """Genera una clave estable a partir de strings y/o bytes (p. ej. la imagen)."""
    h = hashlib.sha256()
    for parte in partes:
        if isinstance(parte, (bytes, bytearray)):
            h.update(parte)
        else:
            h.update(str(parte).encode("utf-8", errors="ignore"))
        h.update(b"|")
    return h.hexdigest()


def obtener(clave):
    """Devuelve el valor cacheado si existe y no ha expirado, si no None."""
    with _lock:
        entrada = _cache.get(clave)
        if not entrada:
            return None
        valor, expira_en = entrada
        if time.time() > expira_en:
            del _cache[clave]
            return None
        return valor


def guardar(clave, valor, ttl_segundos=600):
    """Guarda un valor en caché durante ttl_segundos (10 min por defecto)."""
    with _lock:
        _cache[clave] = (valor, time.time() + ttl_segundos)


def limpiar():
    """Vacía toda la caché (útil para pruebas)."""
    with _lock:
        _cache.clear()


def estado():
    """Información básica de la caché, útil para /status."""
    with _lock:
        return {"entradas": len(_cache)}
