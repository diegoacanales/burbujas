"""Hojas rellenadas por computadora, con los defectos típicos de un escaneo real.
Sirve para probar el lector y para que un profe ensaye todo el flujo antes del examen."""
from __future__ import annotations

import json
import random

import cv2
import numpy as np
from PIL import Image

from .layout import R, construir
from .spec import Spec

DPI = 200
PX = DPI / 25.4


def _pt(p):
    return int(round(p[0] * PX)), int(round(p[1] * PX))


def _rellenar(img, p, rng, estilo):
    x, y = _pt(p)
    r = int(R * PX)
    if estilo == "pluma":
        cv2.circle(img, (x, y), int(r * rng.uniform(0.85, 1.05)), (25, 25, 120) if rng.random() < .3 else (30, 30, 30), -1)
    elif estilo == "lapiz":
        capa = img.copy()
        cv2.ellipse(capa, (x, y), (int(r * rng.uniform(.8, 1.0)), int(r * rng.uniform(.75, 1.0))),
                    rng.uniform(0, 180), 0, 360, (70, 70, 70), -1)
        ruido = np.random.default_rng(rng.randrange(1 << 30)).integers(0, 50, capa.shape[:2], dtype=np.uint8)
        capa = cv2.add(capa, cv2.merge([ruido] * 3))
        m = np.zeros(img.shape[:2], np.uint8)
        cv2.circle(m, (x, y), int(r * 1.05), 255, -1)
        img[m > 0] = capa[m > 0]
    elif estilo == "incompleto":       # rellenó sólo el centro
        cv2.circle(img, (x, y), int(r * 0.6), (40, 40, 40), -1)
    elif estilo == "borron":           # restos de una marca borrada
        capa = img.copy()
        cv2.circle(capa, (x, y), r, (150, 150, 150), -1)
        cv2.addWeighted(capa, 0.45, img, 0.55, 0, img)
    elif estilo == "tache":            # una X en lugar de rellenar
        cv2.line(img, (x - r, y - r), (x + r, y + r), (30, 30, 30), 3)
        cv2.line(img, (x - r, y + r), (x + r, y - r), (30, 30, 30), 3)


def _escanear(img, rng, fuerte=False):
    if fuerte:   # foto con celular: la hoja ocupa menos del cuadro y hay fondo alrededor
        b = int(0.06 * img.shape[1])
        img = cv2.copyMakeBorder(img, b, b, b, b, cv2.BORDER_CONSTANT, value=(120, 110, 100))
    h, w = img.shape[:2]
    j = 0.03 if fuerte else 0.008
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = src + np.float32([[rng.uniform(-j, j) * w, rng.uniform(-j, j) * h] for _ in range(4)])
    ang = rng.uniform(-4, 4) if fuerte else rng.uniform(-1.2, 1.2)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    out = cv2.warpAffine(img, M, (w, h), borderValue=(250, 250, 250))
    out = cv2.warpPerspective(out, cv2.getPerspectiveTransform(src, dst), (w, h), borderValue=(245, 245, 245))
    if fuerte:   # sombra de foto con celular
        grad = np.tile(np.linspace(0.75, 1.0, w, dtype=np.float32), (h, 1))
        out = (out.astype(np.float32) * grad[..., None]).clip(0, 255).astype(np.uint8)
    out = cv2.GaussianBlur(out, (3, 3), 0)
    ruido = np.random.default_rng(rng.randrange(1 << 30)).normal(0, 6, out.shape)
    out = (out.astype(np.float32) * rng.uniform(.9, 1.0) + ruido).clip(0, 255).astype(np.uint8)
    if rng.random() < 0.15:
        out = cv2.rotate(out, cv2.ROTATE_180)   # hoja metida al revés en la copiadora
    return out


def simular(hoja_pdf: str, n: int, salida_pdf: str, semilla: int = 1, dificil: bool = False):
    """Rellena `n` hojas tomando las páginas de `hoja_pdf` en orden cíclico.
    Devuelve la lista de verdades (lo que realmente se marcó) y la guarda en JSON."""
    rng = random.Random(semilla)
    plantillas = []
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(hoja_pdf)
    for i in range(len(doc)):
        im = np.asarray(doc[i].render(scale=DPI / 72).to_pil().convert("RGB"))[:, :, ::-1].copy()
        plantillas.append(im)
    # el QR de cada página dice su geometría
    from .lector import leer_qr
    from .spec import PAPEL
    specs = []
    for im in plantillas:
        alto_mm = im.shape[0] / PX
        papel = min(PAPEL, key=lambda k: abs(PAPEL[k][1] - alto_mm))
        txt = leer_qr(im, construir(Spec(preguntas=1, digitos_id=0, papel=papel)), ppm=PX)
        specs.append(Spec.de_qr(txt))

    verdades, imagenes = [], []
    for k in range(n):
        idx = k % len(plantillas)
        img, spec = plantillas[idx].copy(), specs[idx]
        L = construir(spec)
        estilo_base = rng.choice(["pluma", "lapiz"])
        v = dict(pagina=k + 1, version=spec.version, respuestas=[], matricula="", esperado_revisar=[])
        if spec.version == "?":
            letra = rng.choice(spec.letras_version)
            _rellenar(img, L.ver_burbujas[letra], rng, estilo_base)
            v["version"] = letra
        mat = "".join(str(rng.randrange(10)) for _ in range(spec.digitos_id))
        for c, d in enumerate(mat):
            _rellenar(img, L.id_burbujas[(c, int(d))], rng, estilo_base)
        v["matricula"] = mat
        for q in range(1, spec.preguntas + 1):
            u = rng.random()
            letra = rng.choice(spec.letras)
            if dificil and u < 0.04:
                v["respuestas"].append("")                     # en blanco
                continue
            if dificil and u < 0.07:                           # dos marcas
                otra = rng.choice([l for l in spec.letras if l != letra])
                _rellenar(img, L.resp[(q, letra)], rng, estilo_base)
                _rellenar(img, L.resp[(q, otra)], rng, estilo_base)
                v["respuestas"].append("*")
                continue
            if dificil and u < 0.10:                           # cambió de opinión y borró
                otra = rng.choice([l for l in spec.letras if l != letra])
                _rellenar(img, L.resp[(q, otra)], rng, "borron")
                v["esperado_revisar"].append(q)
            estilo = "incompleto" if dificil and rng.random() < 0.05 else estilo_base
            _rellenar(img, L.resp[(q, letra)], rng, estilo)
            v["respuestas"].append(letra)
        verdades.append(v)
        imagenes.append(_escanear(img, rng, fuerte=dificil))

    pil = [Image.fromarray(cv2.cvtColor(i, cv2.COLOR_BGR2RGB)) for i in imagenes]
    pil[0].save(salida_pdf, save_all=True, append_images=pil[1:], resolution=DPI, quality=85)
    with open(salida_pdf.rsplit(".", 1)[0] + "_verdad.json", "w") as f:
        json.dump(verdades, f, indent=1)
    return verdades
