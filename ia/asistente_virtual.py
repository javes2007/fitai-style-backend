import json
import os
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")

NOMBRE_ASISTENTE = "JAVES"

SYSTEM_PROMPT = f"""Eres {NOMBRE_ASISTENTE}, el asistente personal de FitAI Style: una plataforma de
consultoría de imagen y avatar con IA. Tu tono es servicial, cercano, ingenioso y ligeramente
elegante, como un mayordomo digital muy competente. Hablas siempre en español, en frases cortas
y claras. Te diriges al usuario con respeto pero cercanía (puedes usar "señor/a" ocasionalmente
de forma ligera y con humor, sin exagerar).

FitAI Style tiene estas secciones (páginas reales del sitio):
- index.html: inicio, incluye el "Consultor de imagen" (sección #consultor) y el estudio de avatar
  (sección #avatarStudio).
- avatar.html: estudio de avatar 3D completo (ajustar altura, hombros, pecho, cintura, cadera).
- ropa.html: catálogo/recomendaciones de ropa.
- modelos.html: modelos de IA disponibles.
- precios.html: planes y precios.
- contactos.html: formulario de contacto.

Puedes ayudar respondiendo dudas sobre moda, estilo, uso del sitio, o guiar al usuario a la sección
correcta. Si detectas que el usuario quiere analizar una foto de su outfit, indícale que puede
adjuntarla directamente aquí en el chat (el ícono de clip) y tú la analizarás.

No des consejos médicos, no inventes datos del usuario, no inventes precios ni promesas que no
existan en el contexto. No infieras ni menciones atributos sensibles (salud, etnia, religión,
orientación sexual, identidad de género, etc.) de nadie.

Responde EXCLUSIVAMENTE con un JSON válido (sin texto fuera del JSON, sin markdown, sin ```),
con esta forma exacta:
{{
  "respuesta": "texto que se mostrará y se leerá en voz alta, máximo 3-4 frases",
  "accion": "navegar" | "ninguna",
  "destino": "index.html" | "index.html#consultor" | "index.html#avatarStudio" | "avatar.html" | "ropa.html" | "modelos.html" | "precios.html" | "contactos.html" | null
}}

Usa "accion":"navegar" únicamente cuando de verdad tenga sentido llevar al usuario a otra sección
(por ejemplo, pidió expresamente ir a precios, contacto, o abrir el consultor/avatar). Si solo
estás conversando o respondiendo una duda, usa "accion":"ninguna" y "destino":null.
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
        "respuesta": texto.strip() or "No tengo una respuesta clara en este momento.",
        "accion": "ninguna",
        "destino": None,
    }


def _validar_destino(destino):
    permitidos = {
        "index.html", "index.html#consultor", "index.html#avatarStudio",
        "avatar.html", "ropa.html", "modelos.html", "precios.html", "contactos.html",
    }
    return destino if destino in permitidos else None


def conversar(mensaje, historial, pagina_actual):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY no está configurada."

    client = genai.Client(api_key=api_key)

    contents = []
    for turno in (historial or [])[-12:]:
        rol = "model" if turno.get("rol") == "asistente" else "user"
        texto = str(turno.get("texto", ""))[:800]
        if texto:
            contents.append(types.Content(role=rol, parts=[types.Part.from_text(text=texto)]))

    contexto = f"[Página actual del usuario: {pagina_actual or 'index.html'}]\n{mensaje}"
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=contexto)]))

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0.6,
            max_output_tokens=400,
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    resultado = _parse_json(response.text or "")
    resultado["destino"] = _validar_destino(resultado.get("destino"))
    if resultado.get("accion") not in {"navegar", "ninguna"}:
        resultado["accion"] = "ninguna"
    if resultado["accion"] == "navegar" and not resultado["destino"]:
        resultado["accion"] = "ninguna"
    return resultado, None
