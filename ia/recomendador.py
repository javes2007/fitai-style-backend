import random

def generar_recomendacion(altura=170, tipo_cuerpo=None, estilo_preferido="casual"):
    """Simula un motor de recomendaciones de outfits con Inteligencia Artificial."""
    estilos = {
        "casual": {
            "nombre": "Casual Inteligente",
            "descripcion": "Una combinación cómoda y moderna con una prenda superior de tono claro, pantalones oscuros ajustados y calzado deportivo premium.",
            "ajuste": random.randint(85, 92),
            "recomendacion_score": random.randint(88, 95)
        },
        "formal": {
            "nombre": "Elegante Ejecutivo",
            "descripcion": "Sugerimos un blazer entallado a tus hombros, camisa formal blanca y zapatos clásicos oxford para destacar en ocasiones profesionales.",
            "ajuste": random.randint(88, 95),
            "recomendacion_score": random.randint(90, 97)
        },
        "deportivo": {
            "nombre": "Urbano Deportivo",
            "descripcion": "Ideal para movimiento libre. Prenda superior de secado rápido en tonos grises o negros, joggers y calzado con amortiguación media.",
            "ajuste": random.randint(90, 97),
            "recomendacion_score": random.randint(86, 93)
        }
    }
    
    # Tomamos el estilo por defecto o uno aleatorio si no es válido
    estilo = estilo_preferido if estilo_preferido in estilos else "casual"
    return estilos[estilo]
