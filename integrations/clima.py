"""
clima.py
--------
Integración con OpenWeatherMap: detecta el clima real por coordenadas
para autocompletar el campo "clima" del Consultor de imagen, en vez de
que el usuario lo adivine a ojo.

Requiere la variable de entorno OPENWEATHER_API_KEY (gratis, hasta
1000 llamadas/día): https://openweathermap.org/api
"""

import os
import requests  # pyright: ignore[reportMissingImports]

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY")
OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"


def _categoria_desde_clima(temp_c, codigo_clima):
    """
    Traduce la respuesta técnica de OpenWeatherMap a una de las 4
    categorías que ya usa el Consultor de imagen: cálido/templado/frío/lluvia.

    codigo_clima sigue las convenciones de OpenWeatherMap:
    2xx tormenta, 3xx llovizna, 5xx lluvia, 6xx nieve, 7xx atmósfera (niebla, etc.)
    """
    if codigo_clima is not None and 200 <= codigo_clima < 700:
        return "lluvia"

    if temp_c is None:
        return "templado"

    if temp_c <= 15:
        return "frío"

    if temp_c <= 22:
        return "templado"

    return "cálido"


def obtener_clima(lat, lon):
    """
    Consulta el clima actual por coordenadas.
    Devuelve (datos, None) si funciona, o (None, mensaje_error) si falla.
    """

    if not OPENWEATHER_API_KEY:
        return None, "El clima automático no está configurado (falta OPENWEATHER_API_KEY)."

    try:
        respuesta = requests.get(
            OPENWEATHER_URL,
            params={
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "es",
            },
            timeout=6,
        )
    except requests.RequestException as error:
        return None, f"No se pudo contactar el servicio de clima: {error}"

    if respuesta.status_code != 200:
        return None, "No se pudo obtener el clima para esa ubicación."

    datos = respuesta.json()
    temp = (datos.get("main") or {}).get("temp")
    clima_info = (datos.get("weather") or [{}])[0]
    codigo_clima = clima_info.get("id")

    return {
        "temperatura": round(temp) if temp is not None else None,
        "descripcion": clima_info.get("description", ""),
        "categoria": _categoria_desde_clima(temp, codigo_clima),
        "ciudad": datos.get("name", ""),
    }, None
