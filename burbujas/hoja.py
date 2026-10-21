"""Dibuja la hoja de burbujas en PDF, directo con reportlab (sin LaTeX)."""
from __future__ import annotations

import json
import os

import segno
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .layout import MARCA, R, Layout, a_json, construir
from .spec import Config, Spec

GRIS = 0.5     # etiquetas dentro de las burbujas: legibles pero con poca tinta


def _y(L: Layout, y: float) -> float:
    return (L.alto - y) * mm


def _texto(c, L, x, y, s, fuente="Helvetica", tam=9, gris=0.0, alinear="izq"):
    c.setFillGray(gris)
    c.setFont(fuente, tam)
    if alinear == "izq":
        c.drawString(x * mm, _y(L, y), s)
    elif alinear == "der":
        c.drawRightString(x * mm, _y(L, y), s)
    else:
        c.drawCentredString(x * mm, _y(L, y), s)


def _burbuja(c, L, x, y, etiqueta="", relleno=False):
    c.setLineWidth(0.5)
    c.setStrokeGray(0)
    if relleno:
        c.setFillGray(0)
        c.circle(x * mm, _y(L, y), R * mm, stroke=1, fill=1)
        return
    c.circle(x * mm, _y(L, y), R * mm, stroke=1, fill=0)
    if etiqueta:
        _texto(c, L, x, y + 0.85, etiqueta, "Helvetica-Bold", 6.5, GRIS, "centro")


def _qr(c, L: Layout, texto: str):
    x0, y0, lado = L.qr
    q = segno.make(texto, error="m", micro=False)
    filas = list(q.matrix_iter(border=2))
    n = len(filas)
    m = lado / n
    c.setFillGray(0)
    for i, fila in enumerate(filas):
        for j, v in enumerate(fila):
            if v:
                c.rect((x0 + j * m) * mm, _y(L, y0 + (i + 1) * m), m * mm + 0.05, m * mm + 0.05,
                       stroke=0, fill=1)


def _ajustar(s, fuente, tam, ancho_mm):
    while tam > 7 and stringWidth(s, fuente, tam) > ancho_mm * mm:
        tam -= 0.5
    return tam


def _envolver(s, fuente, tam, ancho_mm):
    lineas, actual = [], ""
    for p in s.split():
        prueba = (actual + " " + p).strip()
        if stringWidth(prueba, fuente, tam) <= ancho_mm * mm:
            actual = prueba
        else:
            lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas


def dibujar_pagina(c, cfg: Config, spec: Spec):
    L = construir(spec)
    XL, XR = 20.0, L.ancho - 20.0
    qx = L.qr[0]

    # marcas de las esquinas y barra de orientación
    c.setFillGray(0)
    for (x, y) in L.marcas:
        c.rect((x - MARCA / 2) * mm, _y(L, y + MARCA / 2), MARCA * mm, MARCA * mm, stroke=0, fill=1)
    x0, y0, x1, y1 = L.barra
    c.rect(x0 * mm, _y(L, y1), (x1 - x0) * mm, (y1 - y0) * mm, stroke=0, fill=1)
    _qr(c, L, spec.a_qr())

    # encabezado
    ancho_tit = qx - XL - (34 if spec.version not in "-?" else 6)
    if cfg.titulo:
        t = _ajustar(cfg.titulo, "Helvetica-Bold", 15, ancho_tit)
        _texto(c, L, XL, 24, cfg.titulo, "Helvetica-Bold", t)
    if cfg.curso:
        t = _ajustar(cfg.curso, "Helvetica", 10, ancho_tit)
        _texto(c, L, XL, 30.5, cfg.curso, "Helvetica", t)
    if spec.version not in "-?":
        _texto(c, L, qx - 4, 22.5, "Versión", "Helvetica", 9, 0, "der")
        _texto(c, L, qx - 4, 33, spec.version, "Helvetica-Bold", 26, 0, "der")
    _texto(c, L, XL, 41, "Nombre:", "Helvetica-Bold", 10)
    c.setLineWidth(0.5)
    c.setStrokeGray(0)
    c.line((XL + 17) * mm, _y(L, 42), (qx - 4) * mm, _y(L, 42))

    lineas = _envolver(cfg.instrucciones, "Helvetica", 8, XR - XL - 22)
    for i, s in enumerate(lineas[:2]):
        _texto(c, L, XL, 48 + i * 3.6, s, "Helvetica", 8, 0.15)
    _burbuja(c, L, XR - 13, 48.5, relleno=True)
    _texto(c, L, XR - 9.5, 49.5, "así", "Helvetica", 8, 0.15)
    c.setLineWidth(0.3)
    c.line(XL * mm, _y(L, 55.5), XR * mm, _y(L, 55.5))

    # matrícula
    if L.id_burbujas:
        ex, ey = L.id_etiqueta
        et = cfg.etiqueta_id + (f"   {cfg.prefijo_id}" if cfg.prefijo_id else "")
        _texto(c, L, ex, ey + 2, et, "Helvetica-Bold", 9)
        c.setLineWidth(0.5)
        for (x, y) in L.id_cajas:
            c.rect((x - 3) * mm, _y(L, y + 3.2), 6 * mm, 6.4 * mm, stroke=1, fill=0)
        for (col, d), (x, y) in L.id_burbujas.items():
            _burbuja(c, L, x, y, str(d))
    if L.ver_burbujas:
        ex, ey = L.ver_etiqueta
        _texto(c, L, ex, ey + 1.2, "Versión", "Helvetica-Bold", 9, 0, "der")
        for letra, (x, y) in L.ver_burbujas.items():
            _burbuja(c, L, x, y, letra, relleno=(letra == spec.version))

    # respuestas
    _texto(c, L, L.resp_etiqueta[0], L.resp_etiqueta[1] + 2, "Respuestas", "Helvetica-Bold", 9)
    for q, (x, y) in L.num.items():
        _texto(c, L, x, y + 1.1, str(q), "Helvetica-Bold", 9, 0, "der")
    for (q, letra), (x, y) in L.resp.items():
        _burbuja(c, L, x, y, letra)

    pie = f"{spec.examen}" + (f" · versión {spec.version}" if spec.version not in "-?" else "")
    _texto(c, L, XL, L.alto - 13, pie + " · no doblar ni escribir cerca de los cuadros negros",
           "Helvetica", 6.5, 0.45)
    return L


def generar(cfg: Config, salida_pdf: str, copias: int = 1) -> list[Spec]:
    """Una página por versión (o una genérica). `copias` repite el juego completo, intercalado."""
    specs = cfg.specs()
    from .spec import PAPEL
    W, H = PAPEL[cfg.base.papel]
    c = canvas.Canvas(salida_pdf, pagesize=(W * mm, H * mm))
    c.setTitle(f"Hoja de respuestas {cfg.base.examen}")
    for _ in range(copias):
        for s in specs:
            dibujar_pagina(c, cfg, s)
            c.showPage()
    c.save()
    base = os.path.splitext(salida_pdf)[0]
    with open(base + "_geometria.json", "w") as f:
        json.dump({s.version: a_json(construir(s)) for s in specs}, f, indent=1, ensure_ascii=False)
    return specs


def generar_tex(salida_pdf: str, salida_tex: str):
    """Plantilla mínima para quien arma su examen en LaTeX: inserta la hoja tal cual,
    sin redibujarla, para que la geometría sea idéntica."""
    nombre = os.path.basename(salida_pdf)
    with open(salida_tex, "w") as f:
        f.write(rf"""% Hoja de respuestas generada por burbujas. NO la redibujes: insértala como PDF.
% Pon este archivo junto a {nombre} y copia el \includepdf donde quieras la hoja.
\documentclass[letterpaper]{{article}}
\usepackage{{pdfpages}}
\begin{{document}}
% página 1 = versión A, página 2 = versión B, etc.
\includepdf[pages=1,noautoscale]{{{nombre}}}
% ... aquí sigue el examen de la versión A ...
\end{{document}}
""")
