import math
from typing import Optional
import base64

import cv2  # type: ignore
import mediapipe as mp


mp_pose = mp.solutions.pose


class AnalizadorMedidas:
    """
    Analizador de proporciones corporales utilizando MediaPipe Pose.

    Importante:
    Una fotografía por sí sola no permite obtener centímetros exactos.
    Para escalar las proporciones utilizamos la altura proporcionada por
    el usuario como referencia.
    """

    def __init__(self):
        # Configuración orientada a producción/Render: evitamos el coste
        # excesivo de segmentation y del modelo Pose de máxima complejidad.
        self.pose = mp_pose.Pose(
            static_image_mode=True,
            model_complexity=0,
            enable_segmentation=False,
            min_detection_confidence=0.5
        )
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5
        )

    @staticmethod
    def _extraer_identidad_facial(resultado_rostro, imagen=None):
        """Extrae proporciones faciales 2D para parametrizar el avatar."""
        if not resultado_rostro.multi_face_landmarks:
            return {"detectado": False, "face_width": 0.50, "face_height": 0.50, "eye_spacing": 0.50, "eye_size": 0.50, "nose_length": 0.50, "nose_width": 0.50, "mouth_width": 0.50, "jaw_width": 0.50}

        lm = resultado_rostro.multi_face_landmarks[0].landmark

        def d(a, b):
            return math.sqrt((lm[a].x - lm[b].x) ** 2 + (lm[a].y - lm[b].y) ** 2)

        face_width = max(d(234, 454), 1e-6)
        face_height = max(d(10, 152), 1e-6)
        eye_spacing = d(133, 362) / face_width
        eye_size = ((d(159, 145) + d(386, 374)) / 2) / face_height
        nose_length = d(168, 1) / face_height
        nose_width = d(98, 327) / face_width
        mouth_width = d(61, 291) / face_width

        resultado = {
            "detectado": True,
            "face_width": 0.50,
            "face_height": max(0.0, min(1.0, face_height / 0.55)),
            "eye_spacing": max(0.0, min(1.0, eye_spacing / 0.45)),
            "eye_size": max(0.0, min(1.0, eye_size / 0.20)),
            "nose_length": max(0.0, min(1.0, nose_length / 0.45)),
            "nose_width": max(0.0, min(1.0, nose_width / 0.30)),
            "mouth_width": max(0.0, min(1.0, mouth_width / 0.55)),
            "jaw_width": max(0.0, min(1.0, face_width / 0.50)),
            "skin_tone": 0.50,
            "skin_variation": 0.20,
        }

        if imagen is not None:
            alto, ancho = imagen.shape[:2]
            xs = [max(0.0, min(1.0, lm[i].x)) for i in (234, 454, 10, 152)]
            ys = [max(0.0, min(1.0, lm[i].y)) for i in (234, 454, 10, 152)]
            x0 = max(0, int(min(xs) * ancho - 0.08 * ancho))
            x1 = min(ancho, int(max(xs) * ancho + 0.08 * ancho))
            y0 = max(0, int(min(ys) * alto - 0.10 * alto))
            y1 = min(alto, int(max(ys) * alto + 0.10 * alto))

            if x1 > x0 and y1 > y0:
                face_crop = imagen[y0:y1, x0:x1]
                if face_crop.size:
                    inner = face_crop[
                        int(face_crop.shape[0] * 0.18):int(face_crop.shape[0] * 0.82),
                        int(face_crop.shape[1] * 0.15):int(face_crop.shape[1] * 0.85)
                    ]
                    if inner.size:
                        pixels = inner.reshape(-1, 3)
                        hsv = cv2.cvtColor(inner, cv2.COLOR_BGR2HSV).reshape(-1, 3)
                        mask = (
                            (hsv[:, 1] < 190) &
                            (hsv[:, 2] > 45) &
                            (hsv[:, 2] < 245)
                        )
                        seleccion = pixels[mask]
                        if len(seleccion) >= 20:
                            b, g, r = [int(v) for v in seleccion.mean(axis=0)]
                            resultado["skin_tone"] = round(
                                max(0.0, min(1.0, ((r + g + b) / 3 - 45) / 170)),
                                4
                            )
                            resultado["skin_rgb"] = {"r": r, "g": g, "b": b}
                            resultado["skin_hex"] = "#{:02x}{:02x}{:02x}".format(r, g, b)

                    ok, encoded = cv2.imencode(
                        ".jpg",
                        face_crop,
                        [int(cv2.IMWRITE_JPEG_QUALITY), 88]
                    )
                    if ok:
                        resultado["face_texture_data_url"] = (
                            "data:image/jpeg;base64,"
                            + base64.b64encode(encoded.tobytes()).decode("ascii")
                        )

        return resultado

    @staticmethod
    def distancia(p1, p2):
        """Calcula distancia entre dos puntos normalizados."""
        return math.sqrt(
            (p1.x - p2.x) ** 2 +
            (p1.y - p2.y) ** 2
        )

    @staticmethod
    def _preparar_imagen(imagen):
        """
        Reduce fotografías grandes antes de MediaPipe para evitar picos de
        memoria/CPU en Render. Conservamos la relación de aspecto.
        """
        max_dimension = 768
        alto, ancho = imagen.shape[:2]
        mayor = max(alto, ancho)

        if mayor <= max_dimension:
            return imagen

        escala = max_dimension / float(mayor)
        nuevo_ancho = max(1, int(ancho * escala))
        nuevo_alto = max(1, int(alto * escala))

        return cv2.resize(
            imagen,
            (nuevo_ancho, nuevo_alto),
            interpolation=cv2.INTER_AREA
        )

    def analizar(self, imagen_path: str, altura_cm: float = 170):
        """
        Analiza una imagen y devuelve puntos corporales y proporciones.
        """

        if not imagen_path:
            raise ValueError("No se proporcionó una imagen.")

        imagen = cv2.imread(imagen_path)

        if imagen is None:
            raise ValueError(
                f"No se pudo leer la imagen: {imagen_path}"
            )

        imagen = self._preparar_imagen(imagen)

        imagen_rgb = cv2.cvtColor(
            imagen,
            cv2.COLOR_BGR2RGB
        )

        resultado = self.pose.process(imagen_rgb)
        resultado_rostro = self.face_mesh.process(imagen_rgb)
        identidad_facial = self._extraer_identidad_facial(resultado_rostro, imagen)

        if not resultado.pose_landmarks:
            return {
                "detectado": False,
                "precision": 0,
                "mensaje": "No se pudo detectar el cuerpo completo."
            }

        landmarks = resultado.pose_landmarks.landmark

        nariz = landmarks[mp_pose.PoseLandmark.NOSE]
        hombro_izq = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
        hombro_der = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
        cadera_izq = landmarks[mp_pose.PoseLandmark.LEFT_HIP]
        cadera_der = landmarks[mp_pose.PoseLandmark.RIGHT_HIP]
        rodilla_izq = landmarks[mp_pose.PoseLandmark.LEFT_KNEE]
        rodilla_der = landmarks[mp_pose.PoseLandmark.RIGHT_KNEE]
        tobillo_izq = landmarks[mp_pose.PoseLandmark.LEFT_ANKLE]
        tobillo_der = landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE]

        landmarks_usados = [
            nariz, hombro_izq, hombro_der, cadera_izq, cadera_der,
            rodilla_izq, rodilla_der, tobillo_izq, tobillo_der
        ]
        precision = round(
            100 * sum(float(p.visibility) for p in landmarks_usados) / len(landmarks_usados),
            1
        )

        hombros_x = (hombro_izq.x + hombro_der.x) / 2
        hombros_y = (hombro_izq.y + hombro_der.y) / 2
        caderas_x = (cadera_izq.x + cadera_der.x) / 2
        caderas_y = (cadera_izq.y + cadera_der.y) / 2

        ancho_hombros_relativo = self.distancia(hombro_izq, hombro_der)
        ancho_cadera_relativo = self.distancia(cadera_izq, cadera_der)

        longitud_torso_relativa = math.sqrt(
            (hombros_x - caderas_x) ** 2 +
            (hombros_y - caderas_y) ** 2
        )

        pierna_izq_relativa = (
            self.distancia(cadera_izq, rodilla_izq)
            + self.distancia(rodilla_izq, tobillo_izq)
        )

        pierna_der_relativa = (
            self.distancia(cadera_der, rodilla_der)
            + self.distancia(rodilla_der, tobillo_der)
        )

        pierna_promedio = (pierna_izq_relativa + pierna_der_relativa) / 2

        y_min = min(nariz.y, hombro_izq.y, hombro_der.y)
        y_max = max(tobillo_izq.y, tobillo_der.y)
        longitud_cuerpo = max(y_max - y_min, 0.001)

        factor_escala = altura_cm / longitud_cuerpo

        ancho_hombros_cm = ancho_hombros_relativo * factor_escala
        ancho_cadera_cm = ancho_cadera_relativo * factor_escala
        torso_cm = longitud_torso_relativa * factor_escala
        pierna_cm = pierna_promedio * factor_escala

        puntos = {
            "nariz": {
                "x": round(nariz.x, 5),
                "y": round(nariz.y, 5),
                "z": round(nariz.z, 5)
            },
            "hombro_izquierdo": {
                "x": round(hombro_izq.x, 5),
                "y": round(hombro_izq.y, 5),
                "z": round(hombro_izq.z, 5)
            },
            "hombro_derecho": {
                "x": round(hombro_der.x, 5),
                "y": round(hombro_der.y, 5),
                "z": round(hombro_der.z, 5)
            },
            "cadera_izquierda": {
                "x": round(cadera_izq.x, 5),
                "y": round(cadera_izq.y, 5),
                "z": round(cadera_izq.z, 5)
            },
            "cadera_derecha": {
                "x": round(cadera_der.x, 5),
                "y": round(cadera_der.y, 5),
                "z": round(cadera_der.z, 5)
            }
        }

        return {
            "detectado": True,
            "precision": precision,
            "altura_cm": round(float(altura_cm), 2),
            "medidas_estimadas": {
                "ancho_hombros_cm": round(ancho_hombros_cm, 2),
                "ancho_cadera_cm": round(ancho_cadera_cm, 2),
                "torso_cm": round(torso_cm, 2),
                "pierna_cm": round(pierna_cm, 2)
            },
            "proporciones": {
                "hombros": round(ancho_hombros_relativo, 5),
                "cadera": round(ancho_cadera_relativo, 5),
                "torso": round(longitud_torso_relativa, 5),
                "piernas": round(pierna_promedio, 5)
            },
            "puntos_mapeados": puntos,
            "identidad_facial": identidad_facial,
            "avatar": {
                "altura": round(float(altura_cm), 2),
                "escala_hombros": round(ancho_hombros_relativo / longitud_cuerpo, 5),
                "escala_cadera": round(ancho_cadera_relativo / longitud_cuerpo, 5),
                "escala_torso": round(longitud_torso_relativa / longitud_cuerpo, 5),
                "escala_piernas": round(pierna_promedio / longitud_cuerpo, 5)
            }
        }


analizador_medidas = AnalizadorMedidas()


def analizar_medidas(imagen_path: str, altura_cm: float = 170):
    """
    Función sencilla para utilizar el analizador desde otros archivos.
    """
    return analizador_medidas.analizar(imagen_path, altura_cm)
