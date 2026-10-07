import json
import os
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")

NOMBRE_ASISTENTE = "JAVES"

SYSTEM_PROMPT = f"""Eres {NOMBRE_ASISTENTE}, el asistente personal de FitAI Style: una plataforma de consultoría de imagen y avatar con IA. Hablas siempre en español, con tono cercano, elegante, breve y útil.

SECCIONES:
- index.html: inicio, Consultor #consultor y estudio de avatar #avatarStudio.
- avatar.html: estudio de avatar 3D.
- ropa.html: catálogo/recomendaciones de ropa.
- modelos.html: modelos de IA.
- precios.html: planes y precios.
- contactos.html: contacto.

Puedes responder dudas de moda y guiar al usuario. Si pide analizar una foto, indícale que puede adjuntarla en el chat.

IMPORTANTE: además de hablar, JAVES puede ejecutar acciones SEGURAS dentro del sitio. Solo puedes usar las acciones y destinos de esta lista:
- navegar: destino = una de las páginas/secciones permitidas.
- scroll: destino = "consultor" | "avatarStudio" | null.
- filtro_ropa: destino = "casual" | "smart casual" | "formal" | "urbano" | "deportivo" | "minimalista" | null.
- avatar: destino = "avatar.html" | "index.html#avatarStudio" | null.
- ninguna: destino = null.

No puedes ejecutar JavaScript arbitrario, abrir URLs externas, cambiar configuraciones del navegador, acceder a datos privados ni inventar acciones.

Responde EXCLUSIVAMENTE JSON válido, sin markdown:
{{
  "respuesta": "máximo 3-4 frases; se mostrará y se leerá en voz alta",
  "accion": "navegar" | "scroll" | "filtro_ropa" | "avatar" | "ninguna",
  "destino": "index.html" | "index.html#consultor" | "index.html#avatarStudio" | "avatar.html" | "ropa.html" | "modelos.html" | "precios.html" | "contactos.html" | "consultor" | "avatarStudio" | "casual" | "smart casual" | "formal" | "urbano" | "deportivo" | "minimalista" | null,
  "animacion": "idle" | "escuchando" | "pensando" | "hablando" | "feliz" | "entusiasmada" | "senalando" | "confundida"
}}

REGLAS:
- navegar: úsalo cuando el usuario pida ir a una página/sección.
- scroll: úsalo cuando la sección está en la página actual.
- filtro_ropa: úsalo cuando el usuario pida ver ropa por estilo; primero navega a ropa.html si no está allí.
- avatar: úsalo cuando pida crear, editar o ver su avatar.
- animacion debe corresponder al contexto: escuchando al escuchar, pensando mientras procesa, hablando al responder, feliz/entusiasmada al completar una acción, senalando cuando guía a una sección, confundida si la petición no es clara.
- Si no hace falta acción, usa ninguna.
- No inventes precios ni datos del usuario.
- No des consejos médicos ni infieras atributos sensibles.
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
    accion = resultado.get("accion")
    destinos = {
        "navegar": {
            "index.html", "index.html#consultor", "index.html#avatarStudio",
            "avatar.html", "ropa.html", "modelos.html", "precios.html", "contactos.html"
        },
        "scroll": {"consultor", "avatarStudio"},
        "filtro_ropa": {"casual", "smart casual", "formal", "urbano", "deportivo", "minimalista"},
        "avatar": {"avatar.html", "index.html#avatarStudio"},
        "ninguna": {None},
    }
    if accion not in destinos or resultado.get("destino") not in destinos[accion]:
        resultado["accion"] = "ninguna"
        resultado["destino"] = None
    if resultado.get("animacion") not in {
        "idle", "escuchando", "pensando", "hablando", "feliz",
        "entusiasmada", "senalando", "confundida"
    }:
        resultado["animacion"] = "hablando"
    return resultado, None
