import json
import os
import time
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
FALLBACK_MODELS = [MODEL, "gemini-3.6-flash", "gemini-3.5-flash-lite"]
MAX_RETRIES_PER_MODEL = 1

SYSTEM_PROMPT = """Eres FitAI Style, un consultor profesional de imagen y vestimenta.
Analiza la ropa visible, colores, combinación, ocasión y coherencia del outfit. Da recomendaciones prácticas y amables.
No infieras ni describas atributos sensibles o privados (salud, etnia, religión, orientación sexual, identidad de género, etc.).
No inventes medidas corporales exactas. Si la foto no permite evaluar algo, dilo claramente.
Responde exclusivamente en JSON válido con estas claves: resumen, paleta, prendas_recomendadas, outfit_sugerido, accesorios, nivel_confianza.
"""

def _parse_json(texto):
    try:
        return json.loads(texto)
    except Exception:
        inicio = texto.find("{")
        fin = texto.rfind("}")
        if inicio >= 0 and fin > inicio:
            try:
                return json.loads(texto[inicio:fin + 1])
            except Exception:
                pass
    return {
        "resumen": texto.strip(),
        "paleta": [],
        "prendas_recomendadas": [],
        "outfit_sugerido": "Consulta generada por IA.",
        "accesorios": [],
        "nivel_confianza": 70
    }

def consultar_imagen(imagen_bytes, mime_type, contexto):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY no está configurada."

    client = genai.Client(api_key=api_key)
    prompt = f"""{SYSTEM_PROMPT}

Contexto del usuario:
- ocasión: {contexto.get('ocasion', 'diario')}
- estilo deseado: {contexto.get('estilo', 'casual')}
- clima: {contexto.get('clima', 'cálido')}
- presupuesto: {contexto.get('presupuesto', 'medio')}

Evalúa la imagen y propone una mejora de vestimenta sin juzgar a la persona."""

    modelos = list(dict.fromkeys(FALLBACK_MODELS))
    ultimo_error = None

    for model in modelos:
        for intento in range(MAX_RETRIES_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=imagen_bytes, mime_type=mime_type),
                        prompt,
                    ],
                    config=types.GenerateContentConfig(
                        temperature=0.55,
                        max_output_tokens=1200,
                    ),
                )
                return _parse_json(response.text or "No se recibió respuesta."), None
            except Exception as exc:
                ultimo_error = exc
                texto_error = str(exc).upper()
                temporal = any(x in texto_error for x in ("UNAVAILABLE", "RESOURCE_EXHAUSTED", "503", "429"))
                if not temporal:
                    raise
                if intento < MAX_RETRIES_PER_MODEL:
                    time.sleep(1.2)
        print(f"[FitAI Gemini] modelo agotado temporalmente: {model}")

    if ultimo_error is not None:
        raise ultimo_error
    raise RuntimeError("Gemini no devolvió una respuesta.")
