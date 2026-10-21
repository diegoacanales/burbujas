"""Puente entre la página web y el paquete burbujas (corre dentro de Pyodide).
Todo entra y sale como JSON o bytes; ningún dato sale de la computadora del usuario."""
import base64
import csv
import io
import json

import cv2
import numpy as np

from burbujas.calificar import (CAMPOS, CAMPOS_ANALISIS, analisis, evaluar, fila, leer_clave,
                                marcar_repetidas)
from burbujas.hoja import generar
from burbujas.layout import R
from burbujas.lector import PPM, Lectura, leer_hoja
from burbujas.spec import config_de_dict

ESCALA = 0.5          # la imagen de revisión va a 4 px/mm: ligera y suficiente para ver las marcas


def hoja_pdf(cfg_json: str):
    cfg = config_de_dict(json.loads(cfg_json))
    generar(cfg, "/tmp/hoja.pdf")
    with open("/tmp/hoja.pdf", "rb") as f:
        return f.read()


def leer(buf, ancho: int, alto: int, archivo: str, pagina: int, cfg_json: str = ""):
    if hasattr(buf, "to_py"):            # Uint8Array de JavaScript
        buf = buf.to_py()
    rgba = np.frombuffer(buf, dtype=np.uint8).reshape(alto, ancho, 4)
    img = cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
    respaldo = None
    if cfg_json:
        try:
            respaldo = config_de_dict(json.loads(cfg_json)).specs()[0]
        except Exception:
            respaldo = None
    r = leer_hoja(img, archivo, pagina, respaldo)
    out = dict(archivo=archivo, pagina=pagina, error=r.error, version=r.version, matricula=r.matricula,
               respuestas=r.respuestas, motivos=r.motivos)
    if r.imagen is not None:
        L = r.layout
        chica = cv2.resize(r.imagen, None, fx=ESCALA, fy=ESCALA, interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", chica, [cv2.IMWRITE_JPEG_QUALITY, 82])
        s = PPM * ESCALA
        out.update(
            imagen="data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode(),
            ancho_img=chica.shape[1], alto_img=chica.shape[0], radio=R * s,
            letras=L.spec.letras, preguntas=L.spec.preguntas, versiones=L.spec.letras_version,
            burbujas={str(q): {l: [L.resp[(q, l)][0] * s, L.resp[(q, l)][1] * s] for l in L.spec.letras}
                      for q in range(1, L.spec.preguntas + 1)},
            numeros={str(q): [p[0] * s, p[1] * s] for q, p in L.num.items()},
        )
    return json.dumps(out)


def _csv(campos, filas, dicts=True):
    b = io.StringIO()
    if dicts:
        w = csv.DictWriter(b, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    else:
        w = csv.writer(b)
        w.writerow(campos)
        w.writerows(filas)
    return "﻿" + b.getvalue()          # BOM: Excel abre bien los acentos


def calificar(lecturas_json: str, clave_csv: str, prefijo: str = ""):
    """lecturas: lo que devolvió leer(), ya con las correcciones hechas a mano en la página."""
    lecturas = json.loads(lecturas_json)
    claves, puntos = {}, None
    if clave_csv.strip():
        with open("/tmp/clave.csv", "w", encoding="utf-8") as f:
            f.write(clave_csv)
        claves, puntos = leer_clave("/tmp/clave.csv")
    filas, extra = [], []
    for d in lecturas:
        r = Lectura(d["archivo"], d["pagina"], version=d.get("version", ""), matricula=d.get("matricula", ""),
                    respuestas=list(d.get("respuestas", [])), motivos=list(d.get("motivos", [])),
                    error=d.get("error", ""))
        if r.error:
            filas.append(fila(r, None))
            extra.append(dict(correctas=None))
            continue
        ev = evaluar(r.respuestas, r.version, claves, puntos) if claves else dict(
            aciertos=None, puntos=None, puntos_max="", correctas=None, aviso="")
        if ev["aviso"]:
            r.motivos.append(ev["aviso"])
        f = fila(r, ev, prefijo)
        if d.get("revisada"):
            r.motivos = []
            f = fila(r, ev, prefijo)
            f["motivos"] = "revisada a mano"
        if d.get("corregidos"):
            nota = "corregido a mano: " + ", ".join(d["corregidos"])
            f["motivos"] = "; ".join(x for x in (f["motivos"], nota) if x)
        f["calificacion"] = (round(100 * ev["puntos"] / ev["puntos_max"], 1)
                             if ev["puntos"] is not None and ev["puntos_max"] else "")
        filas.append(f)
        extra.append(dict(correctas=ev["correctas"]))
    marcar_repetidas(filas)
    for f, d in zip(filas, lecturas):
        if d.get("revisada") and "repetida" in f["motivos"] and "revisada" in f["motivos"]:
            f["revisar"] = ""          # el profe ya la vio
    campos = CAMPOS[:8] + ["calificacion"] + CAMPOS[8:]
    an = analisis([(d["version"], d["respuestas"]) for d in lecturas if not d.get("error")], claves) if lecturas else []
    return json.dumps(dict(filas=filas, extra=extra, csv=_csv(campos, filas),
                           csv_analisis=_csv(CAMPOS_ANALISIS, an, dicts=False), analisis=an))
