"""Lee hojas escaneadas o fotografiadas. Sólo visión por computadora clásica (OpenCV):
encuentra los cuatro cuadros de las esquinas, endereza la hoja, lee el QR y mide la tinta
dentro de cada burbuja. Todo lo dudoso se marca para revisión humana; nada se adivina.
"""
from __future__ import annotations

import itertools
import os
from dataclasses import dataclass, field, replace

import cv2
import numpy as np

from .layout import INSET, Layout, R, construir
from .spec import Spec

PPM = 8.0           # píxeles por milímetro en la imagen enderezada (~200 ppp)
DPI = 200


# ------------------------------------------------------------------ entrada
def paginas(ruta: str, dpi: int = DPI):
    """Devuelve (nombre, número de página, imagen BGR) para PDF o imágenes sueltas."""
    ext = os.path.splitext(ruta)[1].lower()
    nombre = os.path.basename(ruta)
    if ext == ".pdf":
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(ruta)
        for i in range(len(doc)):
            img = doc[i].render(scale=dpi / 72).to_pil().convert("RGB")
            yield nombre, i + 1, cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        doc.close()
    else:
        img = cv2.imread(ruta)
        if img is None:
            raise ValueError(f"no pude abrir {ruta}")
        yield nombre, 1, img


# ------------------------------------------------------------------ esquinas
def _candidatos(img, trabajo=1400):
    H, W = img.shape[:2]
    sc = trabajo / max(H, W)
    chica = cv2.resize(img, (int(W * sc), int(H * sc)), interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(chica, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    A = chica.shape[0] * chica.shape[1]
    vistos, out = [], []
    for blk, C in ((61, 15), (91, 18), (121, 22), (41, 12)):
        th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, blk, C)
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        for c in cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]:
            a = cv2.contourArea(c)
            if a < A * 1.0e-4 or a > A * 6e-3:
                continue
            x, y, w, h = cv2.boundingRect(c)
            (_, _), (rw, rh), _ = cv2.minAreaRect(c)
            # un cuadrado sólido llena ~100% de su rectángulo mínimo; un círculo relleno, 78%
            if rw * rh == 0 or not (0.75 < rw / rh < 1.33) or a / (rw * rh) < 0.88:
                continue
            cx, cy = x + w / 2, y + h / 2
            if any(abs(cx - s[0]) < w * .6 and abs(cy - s[1]) < h * .6 for s in vistos):
                continue
            vistos.append((cx, cy))
            out.append((cx / sc, cy / sc, a / sc ** 2, max(w, h) / sc))
    return out


def _anillo(p):
    c = p.mean(0)
    return p[np.argsort(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]))]


def _puntaje(p, aspecto, tol=0.10, partol=0.16):
    q = _anillo(p)
    d = [np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]
    s1, s2 = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
    if min(s1, s2) < 1:
        return -1
    par = abs(d[0] - d[2]) / max(d[0], d[2]) + abs(d[1] - d[3]) / max(d[1], d[3])
    ar = max(s1, s2) / min(s1, s2)
    if abs(ar - aspecto) / aspecto > tol or par > partol:
        return -1
    ang = sum(abs(np.dot(q[i - 1] - q[i], q[(i + 1) % 4] - q[i]) /
                  (np.linalg.norm(q[i - 1] - q[i]) * np.linalg.norm(q[(i + 1) % 4] - q[i]) + 1e-9))
              for i in range(4))
    if ang > 0.5:
        return -1
    return s1 * s2 * (1 - par) * (1 - ang / 4)


def encontrar_marcas(img, ancho, alto):
    aspecto = (alto - 2 * INSET) / (ancho - 2 * INSET)
    cand = sorted(_candidatos(img), key=lambda t: -t[2])[:24]
    mejor = None
    for combo in itertools.combinations(range(len(cand)), 4):
        tam = [cand[i][3] for i in combo]
        if max(tam) / min(tam) > 1.7:
            continue
        p = np.array([[cand[i][0], cand[i][1]] for i in combo], np.float32)
        s = _puntaje(p, aspecto)
        if s > 0 and (mejor is None or s > mejor[0]):
            mejor = (s, p)
    return None if mejor is None else _anillo(mejor[1])


# ------------------------------------------------------------------ enderezar
def _px(p):
    return p[0] * PPM, p[1] * PPM


def _tinta_zona(g, x0, y0, x1, y1):
    z = g[int(y0 * PPM):int(y1 * PPM), int(x0 * PPM):int(x1 * PPM)]
    return 0.0 if z.size == 0 else float(1 - z.mean() / 255)


def enderezar(img, quad, ancho, alto, barra):
    """Prueba las cuatro rotaciones y se queda con la que tiene la barra negra arriba a la izquierda."""
    W, H = int(round(ancho * PPM)), int(round(alto * PPM))
    dst = np.array([_px((INSET, INSET)), _px((ancho - INSET, INSET)),
                    _px((ancho - INSET, alto - INSET)), _px((INSET, alto - INSET))], np.float32)
    x0, y0, x1, y1 = barra
    mejor = None
    for k in range(4):
        src = np.roll(quad, k, axis=0).astype(np.float32)
        w = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W, H),
                                borderValue=(255, 255, 255))
        g = cv2.cvtColor(w, cv2.COLOR_BGR2GRAY)
        s = _tinta_zona(g, x0 + 2, y0 + .5, x1 - 2, y1 - .5) - _tinta_zona(
            g, ancho - x1 + 2, alto - y1 + .5, ancho - x0 - 2, alto - y0 - .5)
        if mejor is None or s > mejor[0]:
            mejor = (s, w)
    return mejor[1], mejor[0]


def alineada(w, L: Layout) -> bool:
    """Comprobación independiente: tras enderezar, los cuatro cuadros y la barra deben caer
    exactamente donde se imprimieron, y alrededor de los cuadros debe haber papel blanco."""
    from .layout import MARCA
    g = cv2.cvtColor(w, cv2.COLOR_BGR2GRAY)
    m = MARCA / 2 - 1.2
    for (x, y) in L.marcas:
        if _tinta_zona(g, x - m, y - m, x + m, y + m) < 0.55:
            return False
        if _tinta_zona(g, x + MARCA / 2 + 1, y - m, x + MARCA / 2 + 3, y + m) > 0.35:
            return False
    x0, y0, x1, y1 = L.barra
    return _tinta_zona(g, x0 + 2, y0 + .5, x1 - 2, y1 - .5) > 0.55


def leer_qr(w, L: Layout, ppm: float = PPM):
    """El detector de QR de OpenCV es sensible a la escala y a lo que rodea al código,
    así que se prueban varios recortes, escalas y versiones binarizadas."""
    x0, y0, lado = L.qr
    det = cv2.QRCodeDetector()
    for m in (2.5, 5.0):
        z = w[max(0, int((y0 - m) * ppm)):int((y0 + lado + m) * ppm),
              max(0, int((x0 - m) * ppm)):int((x0 + lado + m) * ppm)]
        if z.size == 0:
            continue
        g = cv2.cvtColor(z, cv2.COLOR_BGR2GRAY) if z.ndim == 3 else z
        _, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        for base in (g, b):
            for f in (1.0, 1.5, 2.0, 0.75, 1.25):
                img = base if f == 1.0 else cv2.resize(base, None, fx=f, fy=f, interpolation=cv2.INTER_NEAREST if base is b else cv2.INTER_LINEAR)
                try:
                    txt, _, _ = det.detectAndDecode(img)
                except cv2.error:
                    txt = ""
                if txt:
                    return txt
    return ""


# ------------------------------------------------------------------ tinta
def oscuridad(w):
    """Canal más oscuro: así la tinta roja o azul cuenta igual que la negra."""
    g = w.min(axis=2).astype(np.float32)
    blanco = max(float(np.percentile(g, 95)), 1.0)
    return np.clip(1 - g / blanco, 0, 1)


def tinta(osc, p, rf=0.62):
    x, y = _px(p)
    rr = R * rf * PPM
    x0, x1 = int(x - rr), int(x + rr) + 1
    y0, y1 = int(y - rr), int(y + rr) + 1
    z = osc[max(0, y0):y1, max(0, x0):x1]
    if z.size == 0:
        return 0.0
    yy, xx = np.ogrid[max(0, y0):y1, max(0, x0):x1]
    m = (xx - x) ** 2 + (yy - y) ** 2 <= rr ** 2
    return float(z[m].mean()) if m.any() else 0.0


@dataclass
class Umbrales:
    vacio: float
    marca: float
    tenue: float


def calibrar(valores: np.ndarray, por_renglon_max: np.ndarray) -> Umbrales:
    """Umbrales de la propia hoja: el nivel de una burbuja vacía (un percentil bajo, porque la mayoría
    están vacías) y el de una rellena (los máximos de los renglones contestados)."""
    vacio = float(np.percentile(valores, 30))   # con 2 opciones, la mitad de las burbujas va rellena
    lleno = float(np.percentile(por_renglon_max, 75))
    rango = lleno - vacio
    if rango < 0.25:                       # hoja casi vacía o marcas muy tenues
        marca = vacio + 0.25
    else:
        marca = vacio + max(0.20, 0.45 * rango)
    tenue = vacio + 0.4 * (marca - vacio)
    return Umbrales(vacio, marca, tenue)


def decidir(vals: dict, U: Umbrales):
    """Devuelve (respuesta, motivo). respuesta: letra, '' en blanco, '*' varias marcas."""
    orden = sorted(vals.items(), key=lambda kv: -kv[1])
    marcadas = [k for k, v in orden if v >= U.marca]
    if len(marcadas) == 1:
        seg = orden[1][1] if len(orden) > 1 else 0
        if seg >= U.tenue:
            return marcadas[0], f"posible borrón en {orden[1][0]}"
        return marcadas[0], ""
    if len(marcadas) > 1:
        return "*", "varias marcas: " + "".join(marcadas)
    if orden and orden[0][1] >= U.tenue:
        return "", f"marca tenue en {orden[0][0]}"
    return "", ""


# ------------------------------------------------------------------ una hoja
@dataclass
class Lectura:
    archivo: str
    pagina: int
    examen: str = ""
    version: str = ""
    matricula: str = ""
    respuestas: list = field(default_factory=list)
    motivos: list = field(default_factory=list)      # cosas que un humano debe ver
    error: str = ""
    imagen: object = None                             # hoja enderezada (para anotar)
    layout: object = None
    tintas: dict = field(default_factory=dict)


def leer_hoja(img, archivo, pagina, spec_respaldo: Spec | None = None) -> Lectura:
    from .spec import PAPEL
    r = Lectura(archivo, pagina)
    # Carta y A4 tienen proporciones parecidas: se buscan las esquinas con ambas y se elige
    # el papel cuya proporción se parece más a la medida. El QR lo confirma después.
    opciones = []
    for p in PAPEL:
        q = encontrar_marcas(img, *PAPEL[p])
        if q is not None:
            d = [np.linalg.norm(q[i] - q[(i + 1) % 4]) for i in range(4)]
            medida = max(d[0] + d[2], d[1] + d[3]) / min(d[0] + d[2], d[1] + d[3])
            ancho, alto = PAPEL[p]
            esperada = (alto - 2 * INSET) / (ancho - 2 * INSET)
            preferido = spec_respaldo is not None and spec_respaldo.papel == p
            opciones.append((abs(medida - esperada) - (0.01 if preferido else 0), p, q))
    if not opciones:
        r.error = "no encontré los cuatro cuadros negros de las esquinas"
        return r
    _, papel, quad = min(opciones, key=lambda t: t[0])
    ancho, alto = PAPEL[papel]

    # la barra y el QR están en la misma posición para cualquier spec del mismo papel
    L0 = construir(Spec(preguntas=1, papel=papel, digitos_id=0))
    w, orient = enderezar(img, quad, ancho, alto, L0.barra)
    if not alineada(w, L0):
        r.error = "la hoja no quedó bien alineada (¿esquina tapada, doblada o fuera del escaneo?)"
        r.imagen = None
        return r
    if orient < 0.25:
        r.motivos.append("orientación dudosa")
    texto = leer_qr(w, L0)
    if texto:
        try:
            spec = Spec.de_qr(texto)
        except (ValueError, KeyError) as e:
            r.error = f"QR ilegible como hoja de burbujas: {e}"
            return r
        if spec.papel != papel:      # la proporción engañó; el QR manda
            papel = spec.papel
            ancho, alto = PAPEL[papel]
            q2 = encontrar_marcas(img, ancho, alto)
            if q2 is None:
                r.error = f"el QR dice papel {papel} pero no encontré sus esquinas"
                return r
            w, _ = enderezar(img, q2, ancho, alto, construir(Spec(preguntas=1, papel=papel, digitos_id=0)).barra)
    elif spec_respaldo is not None:
        spec = spec_respaldo if spec_respaldo.versiones < 2 else replace(spec_respaldo, version="?")
        r.motivos.append("no se leyó el QR; se usó examen.toml")
    else:
        r.error = "no se pudo leer el QR (pasa --config examen.toml para continuar sin él)"
        return r

    L = construir(spec)
    osc = oscuridad(w)
    r.examen, r.imagen, r.layout = spec.examen, w, L
    t = {k: tinta(osc, p) for k, p in L.resp.items()}
    r.tintas = t
    valores = np.array(list(t.values()))
    maxs = np.array([max(t[(q, l)] for l in spec.letras) for q in range(1, spec.preguntas + 1)])
    U = calibrar(valores, maxs)

    for q in range(1, spec.preguntas + 1):
        resp, motivo = decidir({l: t[(q, l)] for l in spec.letras}, U)
        r.respuestas.append(resp)
        if motivo:
            r.motivos.append(f"P{q}: {motivo}")

    if L.id_burbujas:
        dig = []
        for c in range(spec.digitos_id):
            resp, motivo = decidir({str(d): tinta(osc, L.id_burbujas[(c, d)]) for d in range(10)}, U)
            if resp == "":
                dig.append("_")
                r.motivos.append(f"matrícula: columna {c + 1} vacía")
            elif resp == "*":
                dig.append("?")
                r.motivos.append(f"matrícula: columna {c + 1} con varias marcas")
            else:
                dig.append(resp)
                if motivo:
                    r.motivos.append(f"matrícula columna {c + 1}: {motivo}")
        r.matricula = "".join(dig)

    if L.ver_burbujas:
        resp, motivo = decidir({l: tinta(osc, p) for l, p in L.ver_burbujas.items()}, U)
        if resp in ("", "*"):
            r.version = spec.version if spec.version not in "-?" else "?"
            if r.version == "?":
                r.motivos.append("versión sin rellenar o con varias marcas")
        else:
            r.version = resp
            if motivo:
                r.motivos.append(f"versión: {motivo}")
            if texto and spec.version not in "-?" and resp != spec.version:
                r.motivos.append(f"el QR dice versión {spec.version} y las burbujas {resp}")
    else:
        r.version = spec.version
    return r


# ------------------------------------------------------------------ imagen de revisión
def anotar(r: Lectura, clave: list | None, salida: str):
    """Verde: marcada y correcta. Rojo: marcada e incorrecta. Azul: la correcta que no marcó.
    Naranja: renglón que hay que revisar a mano."""
    if r.imagen is None:
        return
    im = r.imagen.copy()
    L = r.layout
    rad = int(R * PPM) + 3
    dudosas = {int(m.split(":")[0][1:]) for m in r.motivos if m.startswith("P") and ":" in m}
    for q in range(1, L.spec.preguntas + 1):
        resp = r.respuestas[q - 1]
        ok = clave[q - 1] if clave and q - 1 < len(clave) else None
        for l in L.spec.letras:
            x, y = map(int, _px(L.resp[(q, l)]))
            if resp == l or (resp == "*" and r.tintas[(q, l)] > 0.3):
                color = (0, 160, 0) if ok and l in ok else (0, 0, 220)
                cv2.circle(im, (x, y), rad, color, 3)
            elif ok and l in ok:
                cv2.circle(im, (x, y), rad, (220, 120, 0), 2)
        if q in dudosas:
            x, y = map(int, _px(L.num[q]))
            cv2.rectangle(im, (x - 60, y - 25), (x + int((12 + 7 * L.spec.opciones) * PPM), y + 25),
                          (0, 140, 255), 3)
    txt = f"{r.archivo} p{r.pagina}  matricula {r.matricula or '-'}  version {r.version}"
    cv2.putText(im, txt, (int(20 * PPM), int((L.alto - 6) * PPM)), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 200), 2)
    cv2.imwrite(salida, im, [cv2.IMWRITE_JPEG_QUALITY, 80])
