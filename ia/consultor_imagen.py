import json
import os
import re

from google import genai
from google.genai import types

MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL",
    os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
)
FALLBACK_MODELS = list(dict.fromkeys([
    MODEL,
    "gemini-3.5-flash-lite",
]))
REQUEST_TIMEOUT_MS = 18000
MAX_COLORES_RECOMENDADOS = 8
MAX_COLORES_COMPLEMENTARIOS = 5
MAX_COLORES_MENOS_RECOMENDADOS = 4

SYSTEM_PROMPT = """Eres el módulo de colorimetría personal de FitAI Style.
Tu única tarea es estimar tono y subtono VISIBLES de la piel del rostro y recomendar colores que puedan armonizar con ellos.
NO analices, describas ni recomiendes prendas, outfit, maquillaje o accesorios. Ignora el fondo y la vestimenta. No identifiques a la persona ni infieras etnia, raza, salud u otros atributos sensibles.
Estima tono_piel como claro, claro-medio, medio, medio-profundo o profundo; subtono_piel como cálido, frío, neutro o difícil de determinar; matiz_piel como dorado, rosado, oliva o no concluyente SOLO si hay señales suficientes.
La foto puede alterar los colores por iluminación, balance de blancos, filtros y cámara. Expresa incertidumbre cuando corresponda.
Genera 6 a 8 colores_recomendados y 3 a 5 colores_complementarios. Cada color debe tener nombre, hex válido y motivo breve. Incluye 2 a 4 colores_menos_recomendados solo con justificación razonable; son orientaciones, no prohibiciones.
Devuelve exclusivamente JSON válido con estas claves: resumen, tono_piel, subtono_piel, matiz_piel, colores_recomendados, colores_complementarios, colores_menos_recomendados, nota_iluminacion, nivel_confianza.
nivel_confianza es un entero de 0 a 100. Si el rostro es pequeño, está oculto o la iluminación es dudosa, baja la confianza y explícalo. No inventes precisión.
"""


def _parse_json(texto):
    texto = str(texto or "").strip()
    try:
        data = json.loads(texto)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            data = json.loads(texto[inicio:fin + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _limitar_texto(valor, defecto, limite=500):
    if not isinstance(valor, str):
        return defecto
    valor = valor.strip()
    return valor[:limite] if valor else defecto


def _normalizar_colores(valor, max_items):
    if not isinstance(valor, list):
        return []
    colores = []
    for item in valor[:max_items]:
        if not isinstance(item, dict):
            continue
        nombre = _limitar_texto(item.get("nombre"), "", 70)
        hex_color = str(item.get("hex") or "").strip().upper()
        motivo = _limitar_texto(item.get("motivo"), "Combínalo según tu gusto y el contraste deseado.", 180)
        if not nombre or not re.fullmatch(r"#(?:[0-9A-F]{6}|[0-9A-F]{3})", hex_color):
            continue
        colores.append({"nombre": nombre, "hex": hex_color, "motivo": motivo})
    return colores


def _normalizar_resultado(data):
    if not isinstance(data, dict):
        data = {}
    try:
        confianza = int(float(data.get("nivel_confianza", 0)))
    except (TypeError, ValueError, OverflowError):
        confianza = 0
    confianza = max(0, min(100, confianza))

    recomendados = _normalizar_colores(data.get("colores_recomendados"), MAX_COLORES_RECOMENDADOS)
    complementarios = _normalizar_colores(data.get("colores_complementarios"), MAX_COLORES_COMPLEMENTARIOS)
    menos = _normalizar_colores(data.get("colores_menos_recomendados"), MAX_COLORES_MENOS_RECOMENDADOS)

    return {
        "resumen": _limitar_texto(data.get("resumen"), "No pude determinar una paleta fiable con esta imagen.", 700),
        "tono_piel": _limitar_texto(data.get("tono_piel"), "No determinado", 60),
        "subtono_piel": _limitar_texto(data.get("subtono_piel"), "Difícil de determinar", 60),
        "matiz_piel": _limitar_texto(data.get("matiz_piel"), "No concluyente", 60),
        "colores_recomendados": recomendados,
        "colores_complementarios": complementarios,
        "colores_menos_recomendados": menos,
        "nota_iluminacion": _limitar_texto(
            data.get("nota_iluminacion"),
            "La iluminación y la cámara pueden cambiar la apariencia del color de la piel.",
            500,
        ),
        "nivel_confianza": confianza,
    }


def _error_reintentable(exc):
    texto = str(exc).upper()
    return any(marca in texto for marca in (
        "NOT_FOUND", "MODEL NOT FOUND", "INVALID_ARGUMENT", "JSON_INVALID",
        "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED",
        "TIMEOUT", "TIMED OUT", "503", "504", "429", "404",
    ))


def consultar_imagen(imagen_bytes, mime_type, contexto=None):
    """Analiza colorimetría de piel con límites de tiempo y respuesta normalizada."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY no está configurada."

    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return None, "Formato no compatible. Usa JPG, PNG o WEBP."
    if not imagen_bytes:
        return None, "La imagen está vacía."

    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
        )
    except Exception:
        raise

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "Analiza exclusivamente la piel visible del rostro de la imagen adjunta. "
        "No uses ropa, estilo, ocasión, clima ni presupuesto para decidir la paleta. "
        "Los códigos HEX deben ser válidos y corresponder al nombre del color."
    )
    ultimo_error = None

    for model in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type),
                    prompt,
                ],
                config=types.GenerateContentConfig(
                    temperature=0.35,
                    max_output_tokens=1200,
                    response_mime_type="application/json",
                ),
            )
            data = _parse_json(response.text or "")
            if data is None:
                raise ValueError("JSON_INVALID: Gemini devolvió una respuesta sin JSON válido.")
            return _normalizar_resultado(data), None
        except Exception as exc:
            ultimo_error = exc
            if not _error_reintentable(exc):
                raise
            print(f"[FitAI colorimetria] modelo {model} falló ({type(exc).__name__}); se probará el respaldo.")

    if ultimo_error is not None:
        raise ultimo_error
    raise RuntimeError("Gemini no devolvió una respuesta.")
