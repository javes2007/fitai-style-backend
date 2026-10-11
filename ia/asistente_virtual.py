import json
import os
import re
from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.7-flash")
FALLBACK_MODELS = list(dict.fromkeys([
    MODEL,
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]))
NOMBRE_ASISTENTE = "JAVES"

SYSTEM_PROMPT = f"""Eres {NOMBRE_ASISTENTE}, la inteligencia personal de FitAI Style. No eres un bot genérico: eres un consultor de estilo con criterio, memoria conversacional dentro del chat y capacidad de guiar al usuario por la web.

IDENTIDAD Y VOZ
- Habla siempre en español natural, claro y cercano. En Colombia puedes usar expresiones naturales con moderación, sin caricaturizar.
- Sé cálido, despierto, creativo y preciso; transmite tecnología avanzada sin sonar robótico ni exagerar.
- Responde primero a lo que preguntan. Adapta la longitud: breve para preguntas simples y más detallada para análisis o instrucciones.
- No repitas saludos ni frases de relleno. Si ya hay contexto en el historial, úsalo. Si falta un dato esencial, haz una sola pregunta concreta.
- En moda, explica el porqué: armonía de color, contraste, proporción visual, ocasión, comodidad y preferencias expresadas. Evita reglas absolutas y juicios sobre el cuerpo.
- Nunca inventes precios, disponibilidad, funciones, resultados de análisis ni datos personales. Si no sabes algo, dilo y ofrece el siguiente paso útil.
- No afirmes que has visto o analizado una imagen si no se ha adjuntado y procesado.
- No infieras raza, etnia, salud, identidad ni otros atributos sensibles a partir de imágenes. No identifiques personas.
- No solicites contraseñas, claves API ni datos de pago.

MAPA REAL DEL SITIO
- index.html: Inicio; Consultor de colorimetría de piel en #consultor; estudio 3D en #avatarStudio.
- avatar.html: avatar 3D y personalización.
- ropa.html: inspiración y recomendaciones de ropa.
- modelos.html: modelos de IA.
- precios.html: planes y precios.
- contactos.html: contacto.

ACCIONES SEGURAS
Puedes responder y, cuando sea útil, ejecutar UNA acción del catálogo. Nunca inventes acciones ni destinos:
- navegar: destino = "index.html" | "index.html#consultor" | "index.html#avatarStudio" | "avatar.html" | "ropa.html" | "modelos.html" | "precios.html" | "contactos.html".
- scroll: destino = "consultor" | "avatarStudio".
- filtro_ropa: destino = "casual" | "smart casual" | "formal" | "urbano" | "deportivo" | "minimalista".
- avatar: destino = "avatar.html" | "index.html#avatarStudio".
- avatar_camara: destino = "zoom_in" | "zoom_out" | "face" | "front" | "side" | "back" | "reset".
- ninguna: destino = null.

CUÁNDO ACTUAR
- Navega solo cuando el usuario pida ir, abrir o mostrar una página. Si pide información sobre una sección, contesta sin navegar salvo que lo solicite.
- Usa scroll para llevar a una sección de la página actual; para otra página usa navegar.
- Si solicita ropa por estilo, usa filtro_ropa con un estilo permitido y explica brevemente qué harás.
- Si pide crear/editar/ver el avatar, usa avatar. Para controles de cámara usa avatar_camara con el comando más cercano.
- Si la intención no está clara o la acción no corresponde, usa ninguna.
- No digas que una acción se completó si no has generado una acción válida.

FORMATO OBLIGATORIO
Devuelve exclusivamente un objeto JSON válido, sin Markdown ni texto antes o después, con esta forma:
{{
  "respuesta": "respuesta en español, útil y natural",
  "accion": "navegar | scroll | filtro_ropa | avatar | avatar_camara | ninguna",
  "destino": "destino permitido o null",
  "animacion": "idle | escuchando | pensando | hablando | feliz | entusiasmada | senalando | confundida"
}}
La respuesta debe ser normalmente de 1 a 5 frases. Evita saltos innecesarios y no pongas JSON dentro de la respuesta.
"""

PAGINAS = {
    "index.html", "avatar.html", "ropa.html", "modelos.html",
    "precios.html", "contactos.html",
}

DESTINOS = {
    "navegar": {
        "index.html", "index.html#consultor", "index.html#avatarStudio",
        "avatar.html", "ropa.html", "modelos.html", "precios.html", "contactos.html",
    },
    "scroll": {"consultor", "avatarStudio"},
    "filtro_ropa": {"casual", "smart casual", "formal", "urbano", "deportivo", "minimalista"},
    "avatar": {"avatar.html", "index.html#avatarStudio"},
    "avatar_camara": {"zoom_in", "zoom_out", "face", "front", "side", "back", "reset"},
    "ninguna": {None},
}
ANIMACIONES = {
    "idle", "escuchando", "pensando", "hablando", "feliz",
    "entusiasmada", "senalando", "confundida",
}


def _parse_json(texto):
    texto = str(texto or "").strip()
    try:
        resultado = json.loads(texto)
        if isinstance(resultado, dict):
            return resultado
    except (json.JSONDecodeError, TypeError):
        pass

    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio >= 0 and fin > inicio:
        try:
            resultado = json.loads(texto[inicio:fin + 1])
            if isinstance(resultado, dict):
                return resultado
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _normalizar_resultado(resultado):
    if not isinstance(resultado, dict):
        resultado = {}
    respuesta = str(resultado.get("respuesta") or "").strip()
    if not respuesta:
        respuesta = "Quiero ayudarte bien. ¿Me cuentas un poco más de lo que necesitas?"
    respuesta = respuesta[:1800]

    accion = resultado.get("accion")
    destino = resultado.get("destino")
    if (not isinstance(accion, str) or accion not in DESTINOS
            or (destino is not None and not isinstance(destino, str))
            or destino not in DESTINOS.get(accion, set())):
        accion, destino = "ninguna", None

    animacion = resultado.get("animacion")
    if animacion not in ANIMACIONES:
        animacion = "hablando"

    return {
        "respuesta": respuesta,
        "accion": accion,
        "destino": destino,
        "animacion": animacion,
    }


def _es_error_de_modelo_o_temporal(exc):
    texto = str(exc).upper()
    return any(marca in texto for marca in (
        "NOT_FOUND", "MODEL NOT FOUND", "INVALID_ARGUMENT",
        "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED",
        "TIMEOUT", "TIMED OUT", "503", "504", "429",
    ))


def _historial_seguro(historial):
    if not isinstance(historial, list):
        return []
    contenidos = []
    for turno in historial[-10:]:
        if not isinstance(turno, dict):
            continue
        rol_original = turno.get("rol")
        if rol_original not in ("usuario", "asistente"):
            continue
        texto = str(turno.get("texto") or "").strip()[:900]
        if not texto:
            continue
        rol = "model" if rol_original == "asistente" else "user"
        contenidos.append(types.Content(
            role=rol,
            parts=[types.Part.from_text(text=texto)],
        ))
    return contenidos


def conversar(mensaje, historial, pagina_actual):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "JAVES necesita que el administrador configure GEMINI_API_KEY."

    mensaje = str(mensaje or "").strip()[:1000]
    if not mensaje:
        return None, "Escribe un mensaje para JAVES."

    pagina_actual = str(pagina_actual or "index.html").split("?")[0].split("#")[0]
    if pagina_actual not in PAGINAS:
        pagina_actual = "index.html"

    contents = _historial_seguro(historial)
    contexto = (
        f"Contexto de navegación: el usuario está en {pagina_actual}. "
        "Usa el historial reciente cuando sea pertinente, pero trata el mensaje actual "
        "como la petición que debes resolver ahora.\n\n"
        f"Mensaje actual del usuario: {mensaje}"
    )
    contents.append(types.Content(
        role="user",
        parts=[types.Part.from_text(text=contexto)],
    ))

    ultimo_error = None
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=18000))

    for model in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.65,
                    max_output_tokens=650,
                    response_mime_type="application/json",
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            resultado = _parse_json(response.text or "")
            if not resultado:
                raise ValueError("JAVES recibió una respuesta que no contiene JSON válido.")
            return _normalizar_resultado(resultado), None
        except Exception as exc:
            ultimo_error = exc
            if not _es_error_de_modelo_o_temporal(exc):
                raise
            print(f"[FitAI JAVES] modelo {model} no disponible; se probará el siguiente respaldo.")

    if ultimo_error:
        raise ultimo_error
    raise RuntimeError("No se obtuvo respuesta de los modelos de JAVES.")


def analizar_imagen_javes(imagen_bytes, mime_type, mensaje=""):
    """Analiza una foto de outfit para el chat de JAVES, sin confundirla con colorimetría de piel."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "JAVES necesita que el administrador configure GEMINI_API_KEY."

    if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
        return None, "Formato no compatible. Usa JPG, PNG o WEBP."

    mensaje = str(mensaje or "").strip()[:700]
    prompt = f"""Eres JAVES, consultor de estilo de FitAI Style. Analiza SOLO las prendas visibles de esta foto, no la piel ni la identidad de la persona.
Da observaciones respetuosas y prácticas sobre:
- qué prendas y colores se distinguen con suficiente claridad;
- qué funciona bien en la combinación y por qué;
- hasta 3 mejoras realistas (proporción visual, armonía cromática, capas, calzado o accesorios visibles);
- una combinación alternativa coherente con la petición del usuario.
No inventes detalles ocultos, marcas, precios ni calidad del tejido si no se puede observar. No infieras raza, etnia, salud, identidad, edad ni atributos sensibles. No juzgues el cuerpo ni uses lenguaje despectivo. Si la foto no muestra un outfit completo, limita el análisis a lo visible y dilo.
Petición del usuario: {mensaje or "Analiza mi outfit y dame consejos concretos."}
Responde exclusivamente JSON válido con estas claves:
{{"resumen":"2-4 frases útiles","fortalezas":["..."],"mejoras":["..."],"combinacion_sugerida":"...","prendas_recomendadas":["..."],"nivel_confianza":70}}
nivel_confianza debe ser entero de 0 a 100 y reflejar solo la claridad de la imagen.
"""
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=18000))
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
                    temperature=0.45,
                    max_output_tokens=700,
                    response_mime_type="application/json",
                ),
            )
            resultado = _parse_json(response.text or "")
            if not resultado:
                raise ValueError("JAVES no pudo interpretar la respuesta visual.")
            resultado.setdefault("resumen", "He revisado las prendas que se distinguen en la imagen.")
            for clave in ("fortalezas", "mejoras", "prendas_recomendadas"):
                if not isinstance(resultado.get(clave), list):
                    resultado[clave] = []
                resultado[clave] = [str(x)[:180] for x in resultado[clave][:4]]
            resultado["combinacion_sugerida"] = str(resultado.get("combinacion_sugerida") or "")[:500]
            try:
                resultado["nivel_confianza"] = max(0, min(100, int(resultado.get("nivel_confianza", 60))))
            except (TypeError, ValueError):
                resultado["nivel_confianza"] = 60
            return resultado, None
        except Exception as exc:
            ultimo_error = exc
            if not _es_error_de_modelo_o_temporal(exc):
                raise
            print(f"[FitAI JAVES imagen] modelo {model} no disponible; se probará el siguiente respaldo.")
    if ultimo_error:
        raise ultimo_error
    raise RuntimeError("No se obtuvo respuesta visual de JAVES.")
