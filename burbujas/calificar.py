"""Clave, correcciones manuales y reportes."""
from __future__ import annotations

import csv
import glob
import os
from collections import Counter, defaultdict

from .lector import Lectura, anotar, leer_hoja, paginas
from .spec import Spec


# ------------------------------------------------------------------ clave
def leer_clave(ruta: str):
    """Acepta dos formatos de CSV (también sirve exportado desde Excel o Google Sheets):

    1) version,clave            2) version,1,2,3,...
       A,CABDA...                  A,C,A,B,...
                                   puntos,1,1,2,...     (fila opcional)

    En el formato 2 una celda puede ser "A|C" (se aceptan ambas) o "*" (pregunta anulada:
    todos reciben el punto). Devuelve ({versión: [conjuntos de letras]}, [puntos] o None).
    """
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        filas = [r for r in csv.reader(f) if r and any(c.strip() for c in r)]
    enc = [c.strip().lower() for c in filas[0]]
    claves, puntos = {}, None
    for fila in filas[1:]:
        ver = fila[0].strip().upper()
        celdas = [c.strip().upper() for c in fila[1:]]
        if enc[1:2] == ["clave"]:
            items = list(celdas[0].replace(" ", ""))
        else:
            items = celdas
        if ver == "PUNTOS":
            puntos = [float(x) if x else 1.0 for x in items]
            continue
        conj = []
        for it in items:
            if it in ("*", "ANULADA"):
                conj.append("*")
            else:
                conj.append(set(p for p in it.split("|") if p))
        claves[ver or "-"] = conj
    return claves, puntos


def clave_para(claves: dict, version: str):
    if version in claves:
        return claves[version]
    if len(claves) == 1:
        return next(iter(claves.values()))
    return None


# ------------------------------------------------------------------ correcciones
def leer_correcciones(ruta: str | None):
    """CSV archivo,pagina,campo,valor. campo: matricula, version o el número de pregunta.
    Para dejar una pregunta en blanco, usa valor vacío."""
    out = defaultdict(dict)
    if not ruta or not os.path.exists(ruta):
        return out
    with open(ruta, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[(r["archivo"].strip(), int(r["pagina"]))][r["campo"].strip().lower()] = (r.get("valor") or "").strip().upper()
    return out


def aplicar(r: Lectura, corr: dict):
    c = corr.get((r.archivo, r.pagina))
    if not c:
        return
    for campo, valor in c.items():
        if campo == "matricula":
            r.matricula = valor
        elif campo == "version":
            r.version = valor
        elif campo.isdigit() and 1 <= int(campo) <= len(r.respuestas):
            r.respuestas[int(campo) - 1] = valor
    r.motivos = [f"corregido a mano ({', '.join(c)})"]


# ------------------------------------------------------------------ todo junto
def calificar(entradas: list[str], ruta_clave: str, salida: str, spec_respaldo: Spec | None = None,
              ruta_correcciones: str | None = None, prefijo_id: str = "", log=print):
    os.makedirs(os.path.join(salida, "revisar"), exist_ok=True)
    claves, puntos = leer_clave(ruta_clave)
    corr = leer_correcciones(ruta_correcciones or os.path.join(salida, "correcciones.csv"))
    archivos = []
    for e in entradas:
        if os.path.isdir(e):
            for ext in ("*.pdf", "*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff"):
                archivos += sorted(glob.glob(os.path.join(e, ext)))
        else:
            archivos.append(e)

    filas, lecturas = [], []
    for ruta in archivos:
        for nombre, pag, img in paginas(ruta):
            r = leer_hoja(img, nombre, pag, spec_respaldo)
            aplicar(r, corr)
            lecturas.append(r)
            if r.error:
                filas.append(dict(archivo=nombre, pagina=pag, matricula="", version="", respuestas="",
                                  aciertos="", puntos="", puntos_max="", revisar="sí", motivos=r.error))
                log(f"  {nombre} p{pag}: ERROR {r.error}")
                continue
            clave = clave_para(claves, r.version)
            n = len(r.respuestas)
            pts = (puntos or [1.0] * n)[:n] + [1.0] * max(0, n - len(puntos or []))
            ac, tot = 0, 0.0
            if clave is None:
                r.motivos.append(f"no hay clave para la versión {r.version}")
            else:
                if len(clave) != n:
                    r.motivos.append(f"la clave tiene {len(clave)} respuestas y la hoja {n}")
                for i, resp in enumerate(r.respuestas):
                    ok = clave[i] if i < len(clave) else set()
                    if ok == "*" or (resp and resp != "*" and resp in ok):
                        ac += 1
                        tot += pts[i]
            anotar(r, [("ABCDEFGH" if c == "*" else "".join(sorted(c))) for c in clave] if clave else None,
                   os.path.join(salida, "revisar", f"{os.path.splitext(nombre)[0]}_p{pag:03d}.jpg"))
            filas.append(dict(
                archivo=nombre, pagina=pag,
                matricula=(prefijo_id + r.matricula) if r.matricula else "",
                version=r.version,
                respuestas="".join(x if x else "." for x in r.respuestas),
                aciertos=ac if clave else "", puntos=round(tot, 2) if clave else "",
                puntos_max=round(sum(pts[:n]), 2),
                revisar="sí" if r.motivos else "", motivos="; ".join(r.motivos)))
            log(f"  {nombre} p{pag}: {filas[-1]['matricula'] or '-':>10} v{r.version} "
                f"{filas[-1]['respuestas']} {ac}/{n}" + ("  << revisar" if r.motivos else ""))

    # matrículas repetidas
    cuenta = Counter(f["matricula"] for f in filas if f["matricula"])
    for f in filas:
        if f["matricula"] and cuenta[f["matricula"]] > 1:
            f["revisar"] = "sí"
            f["motivos"] = (f["motivos"] + "; " if f["motivos"] else "") + "matrícula repetida en otra hoja"

    campos = ["archivo", "pagina", "matricula", "version", "respuestas", "aciertos", "puntos",
              "puntos_max", "revisar", "motivos"]
    with open(os.path.join(salida, "resultados.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=campos)
        w.writeheader()
        w.writerows(filas)

    _analisis(lecturas, claves, os.path.join(salida, "analisis_reactivos.csv"))
    with open(os.path.join(salida, "correcciones.csv"), "a+", newline="", encoding="utf-8") as f:
        f.seek(0)
        if not f.read().strip():
            f.write("archivo,pagina,campo,valor\n")
    return filas


def _analisis(lecturas, claves, ruta):
    """Por versión y pregunta: % de aciertos y cuántos eligieron cada opción."""
    datos = defaultdict(list)
    for r in lecturas:
        if not r.error:
            datos[r.version].append(r.respuestas)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["version", "pregunta", "correcta", "n", "pct_aciertos", "A", "B", "C", "D", "E", "F",
                    "en_blanco", "varias"])
        for ver in sorted(datos):
            clave = clave_para(claves, ver)
            filas = datos[ver]
            for i in range(max(len(x) for x in filas)):
                col = [x[i] if i < len(x) else "" for x in filas]
                c = Counter(col)
                ok = clave[i] if clave and i < len(clave) else None
                if ok == "*":
                    acierto, txt = len(col), "anulada"
                elif ok:
                    acierto, txt = sum(1 for x in col if x and x != "*" and x in ok), "|".join(sorted(ok))
                else:
                    acierto, txt = 0, ""
                w.writerow([ver, i + 1, txt, len(col), round(100 * acierto / len(col), 1),
                            *[c.get(l, 0) for l in "ABCDEF"], c.get("", 0), c.get("*", 0)])
