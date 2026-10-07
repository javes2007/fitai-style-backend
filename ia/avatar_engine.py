"""
Motor paramétrico de avatar de FitAI.

Este módulo NO intenta convertir una fotografía directamente en un humano 3D
hiperrealista. Genera un "Avatar DNA" estable que el frontend/renderer puede
usar para deformar un modelo GLB. Esto mantiene separadas identidad, edad,
cuerpo y materiales.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Any
import math


@dataclass
class AgeProfile:
    age: float
    head_scale: float
    eye_scale: float
    body_height_factor: float
    shoulder_factor: float
    torso_factor: float
    limb_factor: float
    wrinkle: float
    skin_elasticity_loss: float
    hair_gray: float
    posture: float


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, t))


def age_profile(age: float) -> Dict[str, Any]:
    """Devuelve parámetros continuos para 0..100 años."""
    age = max(0.0, min(100.0, float(age)))

    # Puntos de control antropométricos visuales.
    keys = [
        (0,   dict(head_scale=1.30, eye_scale=1.22, body_height_factor=0.52,
                   shoulder_factor=0.48, torso_factor=0.72, limb_factor=0.48,
                   wrinkle=0.00, skin_elasticity_loss=0.00, hair_gray=0.00, posture=0.00)),
        (5,   dict(head_scale=1.20, eye_scale=1.15, body_height_factor=0.64,
                   shoulder_factor=0.62, torso_factor=0.80, limb_factor=0.62,
                   wrinkle=0.00, skin_elasticity_loss=0.00, hair_gray=0.00, posture=0.00)),
        (10,  dict(head_scale=1.12, eye_scale=1.08, body_height_factor=0.76,
                   shoulder_factor=0.74, torso_factor=0.88, limb_factor=0.76,
                   wrinkle=0.00, skin_elasticity_loss=0.00, hair_gray=0.00, posture=0.00)),
        (16,  dict(head_scale=1.05, eye_scale=1.02, body_height_factor=0.91,
                   shoulder_factor=0.90, torso_factor=0.95, limb_factor=0.91,
                   wrinkle=0.00, skin_elasticity_loss=0.03, hair_gray=0.00, posture=0.00)),
        (25,  dict(head_scale=1.00, eye_scale=1.00, body_height_factor=1.00,
                   shoulder_factor=1.00, torso_factor=1.00, limb_factor=1.00,
                   wrinkle=0.02, skin_elasticity_loss=0.05, hair_gray=0.00, posture=0.00)),
        (40,  dict(head_scale=1.01, eye_scale=0.99, body_height_factor=1.00,
                   shoulder_factor=0.99, torso_factor=1.00, limb_factor=1.00,
                   wrinkle=0.16, skin_elasticity_loss=0.15, hair_gray=0.08, posture=0.03)),
        (55,  dict(head_scale=1.03, eye_scale=0.97, body_height_factor=0.99,
                   shoulder_factor=0.96, torso_factor=0.99, limb_factor=0.98,
                   wrinkle=0.42, skin_elasticity_loss=0.32, hair_gray=0.42, posture=0.10)),
        (70,  dict(head_scale=1.05, eye_scale=0.95, body_height_factor=0.97,
                   shoulder_factor=0.92, torso_factor=0.97, limb_factor=0.94,
                   wrinkle=0.72, skin_elasticity_loss=0.55, hair_gray=0.78, posture=0.20)),
        (85,  dict(head_scale=1.07, eye_scale=0.93, body_height_factor=0.94,
                   shoulder_factor=0.88, torso_factor=0.94, limb_factor=0.90,
                   wrinkle=0.92, skin_elasticity_loss=0.75, hair_gray=0.96, posture=0.30)),
        (100, dict(head_scale=1.08, eye_scale=0.92, body_height_factor=0.91,
                   shoulder_factor=0.84, torso_factor=0.92, limb_factor=0.87,
                   wrinkle=1.00, skin_elasticity_loss=0.86, hair_gray=1.00, posture=0.38)),
    ]

    for i in range(len(keys) - 1):
        a, pa = keys[i]
        b, pb = keys[i + 1]
        if a <= age <= b:
            t = (age - a) / (b - a)
            out = {k: _lerp(pa[k], pb[k], t) for k in pa}
            out["age"] = age
            return out

    out = dict(keys[-1][1])
    out["age"] = age
    return out


def normalize_identity(face: Dict[str, float] | None = None) -> Dict[str, float]:
    """
    Normaliza rasgos faciales sin afirmar que una foto 2D permite reconstruir
    medidas anatómicas exactas.
    """
    face = face or {}
    return {
        "face_width": float(face.get("face_width", 0.50)),
        "face_height": float(face.get("face_height", 0.50)),
        "eye_spacing": float(face.get("eye_spacing", 0.50)),
        "eye_size": float(face.get("eye_size", 0.50)),
        "nose_length": float(face.get("nose_length", 0.50)),
        "nose_width": float(face.get("nose_width", 0.50)),
        "mouth_width": float(face.get("mouth_width", 0.50)),
        "jaw_width": float(face.get("jaw_width", 0.50)),
        "skin_tone": float(face.get("skin_tone", 0.50)),
        "skin_variation": float(face.get("skin_variation", 0.20)),
    }


def build_avatar_dna(
    *,
    age: float,
    height_cm: float,
    body: Dict[str, float] | None = None,
    face: Dict[str, float] | None = None,
    hair: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Construye un contrato JSON estable para el avatar."""
    body = body or {}
    hair = hair or {}
    ap = age_profile(age)

    return {
        "version": "3.0",
        "engine": "fitai-avatar-dna",
        "edad": age,
        "age": ap,
        "body": {
            "height_cm": max(50.0, min(250.0, float(height_cm))),
            "shoulder": float(body.get("shoulder", 0.50)),
            "waist": float(body.get("waist", 0.50)),
            "body_ratio": float(body.get("body_ratio", 0.50)),
            "muscle": float(body.get("muscle", 0.50)),
            "body_fat": float(body.get("body_fat", 0.50)),
        },
        "identity": normalize_identity(face),
        "hair": {
            "style": hair.get("style", "default"),
            "color": hair.get("color", "#17141c"),
            "gray": ap["hair_gray"],
        },
        "skin": {
            "tone": normalize_identity(face)["skin_tone"],
            "roughness": 0.46 + 0.20 * ap["skin_elasticity_loss"],
            "subsurface": 0.32 - 0.10 * ap["skin_elasticity_loss"],
            "wrinkle": ap["wrinkle"],
        },
        "render": {
            "mode": "glb-with-procedural-fallback",
            "glb_ready": True,
            "glb_path": "/assets/avatars/human-base.glb",
            "model_url": None,
            "source": "parametric-human",
            "photo_identical": False,
            "age_progression": "parametric-approximation",
        },
    }
