"""
google.py
---------
Servicio de búsqueda de Google para FitAI.

Características:
- Búsquedas asíncronas
- Caché en memoria con TTL
- Búsqueda dirigida por categoría
- Metadatos de resultados
- Control de errores
- API Key mediante variable de entorno
- Compatible con Flask
"""

import os
import time
import hashlib
import asyncio
from typing import Optional, Dict, Any, List

import aiohttp


# ============================================================
# CONFIGURACIÓN
# ============================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# Tiempo de vida del caché
CACHE_TTL = int(os.getenv("GOOGLE_CACHE_TTL", "900"))

# Cantidad máxima de resultados
DEFAULT_RESULTS = int(os.getenv("GOOGLE_DEFAULT_RESULTS", "10"))


# ============================================================
# CACHÉ
# ============================================================

_cache: Dict[str, Dict[str, Any]] = {}


def _cache_key(query: str, **params) -> str:
    """
    Genera una clave única para una búsqueda.
    """

    raw = f"{query}|{sorted(params.items())}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _get_cache(key: str) -> Optional[Any]:
    """
    Obtiene un resultado del caché si todavía es válido.
    """

    data = _cache.get(key)

    if not data:
        return None

    age = time.time() - data["timestamp"]

    if age > CACHE_TTL:
        del _cache[key]
        return None

    return data["value"]


def _set_cache(key: str, value: Any):
    """
    Guarda un resultado en caché.
    """

    _cache[key] = {
        "timestamp": time.time(),
        "value": value
    }


def clear_cache():
    """
    Limpia completamente el caché.
    """

    _cache.clear()


# ============================================================
# VALIDACIÓN
# ============================================================

def _validate_config():
    """
    Verifica que Google esté configurado.
    """

    if not GOOGLE_API_KEY:
        raise RuntimeError(
            "Falta la variable de entorno GOOGLE_API_KEY"
        )

    if not GOOGLE_CSE_ID:
        raise RuntimeError(
            "Falta la variable de entorno GOOGLE_CSE_ID"
        )


# ============================================================
# BÚSQUEDA ASÍNCRONA
# ============================================================

async def google_search(
    query: str,
    *,
    num: int = DEFAULT_RESULTS,
    start: int = 1,
    language: str = "es",
    country: str = "co",
    safe: str = "active",
    site_search: Optional[str] = None
) -> Dict[str, Any]:
    """
    Realiza una búsqueda asíncrona utilizando Google Custom Search.

    Parámetros:
        query:
            Texto que se desea buscar.

        num:
            Cantidad de resultados.

        start:
            Resultado desde el cual comenzar.

        language:
            Idioma de búsqueda.

        country:
            País.

        safe:
            Filtro de contenido.

        site_search:
            Limita la búsqueda a un sitio concreto.
    """

    if not query or not query.strip():
        return {
            "success": False,
            "error": "La consulta de búsqueda está vacía.",
            "results": []
        }

    _validate_config()

    query = query.strip()

    num = max(1, min(num, 10))

    # --------------------------------------------------------
    # CACHÉ
    # --------------------------------------------------------

    cache_key = _cache_key(
        query,
        num=num,
        start=start,
        language=language,
        country=country,
        safe=safe,
        site_search=site_search
    )

    cached = _get_cache(cache_key)

    if cached is not None:
        cached["metadata"]["from_cache"] = True
        return cached

    # --------------------------------------------------------
    # PARÁMETROS
    # --------------------------------------------------------

    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CSE_ID,
        "q": query,
        "num": num,
        "start": start,
        "hl": language,
        "gl": country,
        "safe": safe
    }

    if site_search:
        params["siteSearch"] = site_search

    # --------------------------------------------------------
    # PETICIÓN ASÍNCRONA
    # --------------------------------------------------------

    timeout = aiohttp.ClientTimeout(total=15)

    try:

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                GOOGLE_SEARCH_URL,
                params=params
            ) as response:

                data = await response.json()

                if response.status != 200:

                    error_message = (
                        data.get("error", {})
                        .get("message", "Error desconocido de Google")
                    )

                    return {
                        "success": False,
                        "error": error_message,
                        "status_code": response.status,
                        "results": []
                    }

    except asyncio.TimeoutError:

        return {
            "success": False,
            "error": "Google tardó demasiado en responder.",
            "results": []
        }

    except aiohttp.ClientError as error:

        return {
            "success": False,
            "error": f"Error de conexión con Google: {error}",
            "results": []
        }

    except Exception as error:

        return {
            "success": False,
            "error": f"Error inesperado: {error}",
            "results": []
        }

    # ========================================================
    # PROCESAMIENTO DE RESULTADOS
    # ========================================================

    results: List[Dict[str, Any]] = []

    for index, item in enumerate(
        data.get("items", []),
        start=1
    ):

        results.append({

            "position": index,

            "title": item.get(
                "title",
                ""
            ),

            "url": item.get(
                "link",
                ""
            ),

            "description": item.get(
                "snippet",
                ""
            ),

            "display_url": item.get(
                "displayLink",
                ""
            ),

            "image": (
                (item.get("pagemap", {}).get("cse_image") or [{}])[0].get("src")
                or (item.get("pagemap", {}).get("cse_thumbnail") or [{}])[0].get("src")
            ),

            "formatted_url": item.get(
                "formattedUrl",
                ""
            ),

            "mime": item.get(
                "mime",
                None
            ),

            "file_format": item.get(
                "fileFormat",
                None
            ),

            "html_title": item.get(
                "htmlTitle",
                ""
            ),

            "html_snippet": item.get(
                "htmlSnippet",
                ""
            ),

            "cache_id": item.get(
                "cacheId",
                None
            )
        })

    # ========================================================
    # METADATOS
    # ========================================================

    search_information = data.get(
        "searchInformation",
        {}
    )

    response_data = {

        "success": True,

        "query": query,

        "results": results,

        "metadata": {

            "total_results": search_information.get(
                "formattedTotalResults",
                "0"
            ),

            "search_time": search_information.get(
                "searchTime",
                0
            ),

            "result_count": len(results),

            "from_cache": False,

            "timestamp": time.time(),

            "language": language,

            "country": country,

            "safe_search": safe,

            "site_search": site_search
        }
    }

    # Guardar en caché
    _set_cache(
        cache_key,
        response_data
    )

    return response_data


# ============================================================
# BÚSQUEDA DIRIGIDA PARA FITAI
# ============================================================

async def directed_search(
    query: str,
    category: Optional[str] = None,
    gender: Optional[str] = None,
    style: Optional[str] = None,
    color: Optional[str] = None,
    site: Optional[str] = None,
    num: int = 10
) -> Dict[str, Any]:
    """
    Realiza una búsqueda dirigida para FitAI.

    Ejemplo:

        directed_search(
            "camisa",
            category="ropa",
            gender="hombre",
            style="casual",
            color="negro"
        )

    Generaría una consulta similar a:

        camisa ropa hombre casual negro
    """

    parts = []

    if query:
        parts.append(query)

    if category:
        parts.append(category)

    if gender:
        parts.append(gender)

    if style:
        parts.append(style)

    if color:
        parts.append(color)

    final_query = " ".join(parts)

    return await google_search(
        final_query,
        num=num,
        site_search=site
    )


# ============================================================
# BÚSQUEDA DE ROPA
# ============================================================

async def search_clothing(
    clothing: str,
    gender: Optional[str] = None,
    style: Optional[str] = None,
    color: Optional[str] = None,
    brand: Optional[str] = None,
    num: int = 10
) -> Dict[str, Any]:
    """
    Búsqueda especializada de prendas.
    """

    query_parts = [
        clothing,
        "ropa"
    ]

    if gender:
        query_parts.append(gender)

    if style:
        query_parts.append(style)

    if color:
        query_parts.append(color)

    if brand:
        query_parts.append(brand)

    query = " ".join(query_parts)

    return await google_search(
        query,
        num=num
    )


# ============================================================
# BÚSQUEDA DE IMÁGENES / REFERENCIAS
# ============================================================

async def search_fashion(
    query: str,
    gender: Optional[str] = None,
    style: Optional[str] = None,
    color: Optional[str] = None,
    num: int = 10
) -> Dict[str, Any]:
    """
    Busca referencias relacionadas con moda.
    """

    return await directed_search(
        query=query,
        category="moda",
        gender=gender,
        style=style,
        color=color,
        num=num
    )


# ============================================================
# EJECUCIÓN SIMPLE DESDE PYTHON
# ============================================================

def search_sync(query: str, **kwargs):
    """
    Permite utilizar google_search desde código síncrono.
    """

    return asyncio.run(
        google_search(
            query,
            **kwargs
        )
    )


# ============================================================
# ESTADO DEL SERVICIO
# ============================================================

def service_status() -> Dict[str, Any]:
    """
    Devuelve el estado de configuración del servicio.
    """

    return {

        "service": "Google Custom Search",

        "configured": bool(
            GOOGLE_API_KEY and GOOGLE_CSE_ID
        ),

        "api_key_configured": bool(
            GOOGLE_API_KEY
        ),

        "cse_configured": bool(
            GOOGLE_CSE_ID
        ),

        "cache_entries": len(
            _cache
        ),

        "cache_ttl": CACHE_TTL
    }


# ============================================================
# PRUEBA
# ============================================================

if __name__ == "__main__":

    async def main():

        result = await directed_search(
            query="camisa",
            category="ropa",
            gender="hombre",
            style="casual",
            color="negro"
        )

        print(result)

    asyncio.run(main())