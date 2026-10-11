import json
import os
import time
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
FALLBACK_MODELS = [MODEL, "gemini-3.6-flash", "gemini-3.5-flash-lite"]
MAX_RETRIES_PER_MODEL = 0

SYSTEM_PROMPT = """Eres el módulo de colorimetría personal de FitAI Style.
Tu única tarea en esta solicitud es estimar el tono y subtono VISIBLES de la piel de la persona y recomendar colores que puedan armonizar con ellos.
NO analices, describas ni recomiendes ropa visible, prendas, outfit, maquillaje o accesorios. Ignora el fondo y la vestimenta. No identifiques a la persona ni infieras etnia, raza, salud u otros atributos sensibles.
Estima tono_piel con una categoría descriptiva (claro, claro-medio, medio, medio-profundo o profundo); subtono_piel (cálido, frío, neutro o difícil de determinar); y matiz_piel (por ejemplo dorado, rosado, oliva o no concluyente) SOLO si la imagen ofrece señales suficientes. El color de la piel en una foto puede alterarse por iluminación, balance de blancos, filtros y cámara: no afirmes certeza científica, y reconoce la incertidumbre cuando corresponda.
Genera 6 a 8 colores_recomendados y 3 a 5 colores_complementarios. Cada color debe ser un objeto con nombre, hex (HEX válido) y motivo breve relacionado con armonía/contraste de color. Incluye 2 a 4 colores_menos_recomendados solo si hay una justificación cromática razonable; evita reglas absolutas y aclara que son orientaciones, no prohibiciones. No trates ninguna paleta como universal para una categoría de piel.
Responde exclusivamente en JSON válido con estas claves:
resumen, tono_piel, subtono_piel, matiz_piel, colores_recomendados, colores_complementarios, colores_menos_recomendados, nota_iluminacion, nivel_confianza.
nivel_confianza debe ser un número de 0 a 100. Si el rostro está pequeño, oculto, con filtros fuertes o luz coloreada, baja la confianza y dilo en nota_iluminacion. No inventes precisión que la imagen no permite.
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
        "tono_piel": "No determinado",
        "subtono_piel": "Difícil de determinar",
        "matiz_piel": "No concluyente",
        "colores_recomendados": [],
        "colores_complementarios": [],
        "colores_menos_recomendados": [],
        "nota_iluminacion": "No se pudo interpretar toda la respuesta estructurada. Prueba una foto con luz natural y sin filtros.",
        "nivel_confianza": 0
    }

def consultar_imagen(imagen_bytes, mime_type, contexto):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY no está configurada."

    client = genai.Client(api_key=api_key)
    prompt = f"""{SYSTEM_PROMPT}

Analiza exclusivamente la piel visible del rostro de la imagen adjunta. No uses la ropa, el estilo, la ocasión, el clima ni el presupuesto como señal para decidir la paleta.
Devuelve JSON con las claves y estructura solicitadas. Los colores deben incluir códigos HEX que correspondan visualmente al nombre y motivo de cada color."""

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
                        max_output_tokens=1800,
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
