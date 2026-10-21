"""Prueba de punta a punta: generar hoja -> rellenar por simulación -> leer.

La regla de oro: el lector puede pedir revisión humana, pero nunca debe entregar
una respuesta, matrícula o versión equivocada sin avisar.
"""
import csv
import os

import pytest

from burbujas.calificar import calificar, leer_clave
from burbujas.hoja import generar
from burbujas.lector import leer_hoja, paginas
from burbujas.simular import simular
from burbujas.spec import Config, Spec, leer_config

CASOS = {
    "carta_24x4_preimpresa": dict(base=Spec(24, 4, 8, 4, "?", "carta", "T1"), prefijo_id="A"),
    "a4_50x5_generica": dict(base=Spec(50, 5, 9, 3, "?", "a4", "T2"), version_preimpresa=False),
    "carta_10x2_sin_id_ni_versiones": dict(base=Spec(10, 2, 0, 0, "-", "carta", "T3")),
    "carta_90x4": dict(base=Spec(90, 4, 6, 2, "?", "carta", "T4")),
}


def _revisar(tmp_path, nombre, dificil, semilla):
    cfg = Config(**CASOS[nombre])
    hoja = str(tmp_path / "hoja.pdf")
    generar(cfg, hoja)
    esc = str(tmp_path / "esc.pdf")
    verdad = simular(hoja, 6, esc, semilla=semilla, dificil=dificil)
    for (nom, pag, img), v in zip(paginas(esc), verdad):
        r = leer_hoja(img, nom, pag)
        assert not r.error, f"p{pag}: {r.error}"
        dudosas = {int(m.split(":")[0][1:]) for m in r.motivos if m.startswith("P")}
        for q, (leida, real) in enumerate(zip(r.respuestas, v["respuestas"]), 1):
            assert leida == real or q in dudosas, f"p{pag} P{q}: leí {leida!r}, era {real!r}, sin aviso"
        assert r.matricula == v["matricula"]
        assert r.version == v["version"]
        if not dificil:
            assert not r.motivos, r.motivos


@pytest.mark.parametrize("nombre", list(CASOS))
def test_escaneo_limpio(tmp_path, nombre):
    _revisar(tmp_path, nombre, dificil=False, semilla=5)


@pytest.mark.parametrize("nombre", ["carta_24x4_preimpresa", "a4_50x5_generica"])
@pytest.mark.parametrize("semilla", [1, 2])
def test_foto_dificil(tmp_path, nombre, semilla):
    _revisar(tmp_path, nombre, dificil=True, semilla=semilla)


def test_no_cabe():
    from burbujas.layout import construir
    with pytest.raises(ValueError, match="no caben"):
        construir(Spec(200, 8, 12, 6, "A", "carta", "X"))


def test_qr_ida_y_vuelta():
    s = Spec(37, 5, 7, 3, "B", "a4", "Mi-Examen_2").validar()
    assert Spec.de_qr(s.a_qr()) == s


def test_clave_dos_formatos(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("version,clave\nA,ABCD\nB,DCBA\n")
    b = tmp_path / "b.csv"
    b.write_text("version,1,2,3,4\nA,A,B|C,*,D\npuntos,1,2,1,1\n")
    ca, pa = leer_clave(str(a))
    cb, pb = leer_clave(str(b))
    assert ca["A"] == [{"A"}, {"B"}, {"C"}, {"D"}] and pa is None
    assert cb["A"] == [{"A"}, {"B", "C"}, "*", {"D"}] and pb == [1, 2, 1, 1]


def test_calificar_y_corregir(tmp_path):
    cfg = Config(**CASOS["carta_24x4_preimpresa"])
    hoja = str(tmp_path / "hoja.pdf")
    generar(cfg, hoja)
    esc = str(tmp_path / "esc.pdf")
    verdad = simular(hoja, 4, esc, semilla=9)
    clave = tmp_path / "clave.csv"
    clave.write_text("version,clave\n" + "".join(f"{L},{''.join(v['respuestas'])}\n"
                                                  for L, v in zip("ABCD", verdad)))
    sal = str(tmp_path / "res")
    filas = calificar([esc], str(clave), sal, prefijo_id="A", log=lambda *a: None)
    assert [f["aciertos"] for f in filas] == [24] * 4          # cada hoja contestó su propia clave
    assert filas[0]["matricula"] == "A" + verdad[0]["matricula"]
    # corrección manual: la pregunta 1 de la hoja 1 pasa a otra letra
    otra = "B" if verdad[0]["respuestas"][0] != "B" else "C"
    with open(os.path.join(sal, "correcciones.csv"), "a") as f:
        f.write(f"esc.pdf,1,1,{otra}\n")
    filas = calificar([esc], str(clave), sal, log=lambda *a: None)
    assert filas[0]["aciertos"] == 23 and "corregido a mano" in filas[0]["motivos"]
    with open(os.path.join(sal, "analisis_reactivos.csv"), encoding="utf-8-sig") as f:
        assert len(list(csv.DictReader(f))) == 4 * 24


def test_plantilla_de_ejemplo():
    aqui = os.path.join(os.path.dirname(__file__), "..", "burbujas", "plantillas", "examen.toml")
    cfg = leer_config(aqui)
    assert [s.version for s in cfg.specs()] == list("ABCD")
