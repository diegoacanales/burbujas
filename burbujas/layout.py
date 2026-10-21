"""Geometría de la hoja, en milímetros, con origen en la esquina superior izquierda (y hacia abajo).

El generador dibuja exactamente estas posiciones y el lector las mide. Cualquier cambio
aquí cambia ambas cosas a la vez; por eso el QR lleva un número de formato (BRB1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .spec import PAPEL, Spec

R = 2.4            # radio de la burbuja
PASO = 7.0         # separación entre burbujas de una misma pregunta y entre renglones
PASO_ID = 6.6      # separación vertical de los dígitos de matrícula
GRUPO = 2.5        # espacio extra cada 5 preguntas
MARCA = 6.0        # lado de los cuadros negros de las esquinas
INSET = 12.0       # distancia del centro de cada cuadro al borde del papel
XL_MARGEN = 20.0
CUERPO_Y = 60.0    # donde empieza la zona de respuestas
QR_LADO = 26.0


@dataclass
class Layout:
    spec: Spec
    ancho: float
    alto: float
    marcas: list = field(default_factory=list)        # centros TL, TR, BR, BL
    barra: tuple = ()                                  # (x0, y0, x1, y1) barra de orientación
    qr: tuple = ()                                     # (x0, y0, lado)
    id_burbujas: dict = field(default_factory=dict)    # (col, dígito) -> (x, y)
    id_cajas: list = field(default_factory=list)       # centros de las cajas para escribir
    id_etiqueta: tuple = ()
    ver_burbujas: dict = field(default_factory=dict)   # letra -> (x, y)
    ver_etiqueta: tuple = ()
    resp: dict = field(default_factory=dict)           # (pregunta, letra) -> (x, y)
    num: dict = field(default_factory=dict)            # pregunta -> (x, y) del número
    resp_etiqueta: tuple = ()


def construir(spec: Spec) -> Layout:
    W, H = PAPEL[spec.papel]
    L = Layout(spec=spec, ancho=W, alto=H)
    L.marcas = [(INSET, INSET), (W - INSET, INSET), (W - INSET, H - INSET), (INSET, H - INSET)]
    L.barra = (XL_MARGEN, 13.0, XL_MARGEN + 50.0, 15.5)
    XR = W - XL_MARGEN
    L.qr = (XR - QR_LADO, 15.0, QR_LADO)
    abajo = H - 21.0

    # ---- bloque derecho: matrícula y, si toca, burbujas de versión ----
    bloque_izq = XR
    bloque_abajo = CUERPO_Y
    nd = spec.digitos_id
    if nd:
        x_ult = XR - 3.5
        xs = [x_ult - (nd - 1 - c) * PASO for c in range(nd)]
        L.id_etiqueta = (xs[0] - 3.5, CUERPO_Y + 1.0)
        L.id_cajas = [(x, CUERPO_Y + 7.0) for x in xs]
        y0 = CUERPO_Y + 15.0
        for c, x in enumerate(xs):
            for d in range(10):
                L.id_burbujas[(c, d)] = (x, y0 + d * PASO_ID)
        bloque_izq = xs[0] - 3.5
        bloque_abajo = y0 + 9 * PASO_ID + R
    if spec.versiones >= 2:
        n = spec.versiones
        yv = bloque_abajo + 12.0
        xs = [XR - 3.5 - (n - 1 - i) * PASO for i in range(n)]
        L.ver_etiqueta = (xs[0] - 4.0, yv)
        for i, letra in enumerate(spec.letras_version):
            L.ver_burbujas[letra] = (xs[i], yv)
        bloque_izq = min(bloque_izq, xs[0] - 22.0)
        bloque_abajo = yv + R
    hay_bloque = bool(nd) or spec.versiones >= 2

    # ---- columnas de respuestas ----
    ancho_col = 15.0 + (spec.opciones - 1) * PASO
    sep = 6.0
    ncols = int((XR - XL_MARGEN + sep) // (ancho_col + sep))
    if ncols < 1:
        raise ValueError("demasiadas opciones para el ancho del papel")
    y_ini = CUERPO_Y + 7.0
    columnas = []                                  # (x0, y_inicial)
    for i in range(ncols):
        x0 = XL_MARGEN + i * (ancho_col + sep)
        choca = hay_bloque and x0 + ancho_col > bloque_izq - 4.0
        columnas.append((x0, bloque_abajo + 10.0 if choca else y_ini))

    def y_renglon(y_col, i):
        return y_col + i * PASO + (i // 5) * GRUPO

    def capacidad(y_col):
        n = 0
        while y_renglon(y_col, n) <= abajo:
            n += 1
        return n

    caps = [capacidad(y) for _, y in columnas]
    nq = spec.preguntas
    objetivo = math.ceil(nq / math.ceil(nq / 15))
    while True:
        cupos = [min(objetivo, c) for c in caps]
        if sum(cupos) >= nq:
            break
        if objetivo >= max(caps):
            raise ValueError(f"no caben {nq} preguntas de {spec.opciones} opciones en una hoja "
                             f"(máximo {sum(caps)}); reduce preguntas, opciones o dígitos de matrícula")
        objetivo += 1

    q = 1
    for (x0, y_col), cupo in zip(columnas, cupos):
        for i in range(cupo):
            if q > nq:
                break
            y = y_renglon(y_col, i)
            L.num[q] = (x0 + 7.0, y)
            for k, letra in enumerate(spec.letras):
                L.resp[(q, letra)] = (x0 + 12.0 + k * PASO, y)
            q += 1
    L.resp_etiqueta = (XL_MARGEN, CUERPO_Y + 1.0)
    return L


def a_json(L: Layout) -> dict:
    """Versión serializable, por transparencia y para depurar."""
    return {
        "formato": "BRB1", "unidades": "mm, origen arriba a la izquierda, y hacia abajo",
        "qr": L.spec.a_qr(), "papel": [L.ancho, L.alto], "radio": R, "marcas": L.marcas,
        "matricula": {f"c{c + 1}_d{d}": p for (c, d), p in L.id_burbujas.items()},
        "version": L.ver_burbujas,
        "respuestas": {f"{q}{letra}": p for (q, letra), p in L.resp.items()},
    }
