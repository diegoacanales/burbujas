"""Configuración del examen y el texto que viaja en el código QR.

La geometría de la hoja depende sólo de los campos de `Spec`. El QR lleva esos
mismos campos, así que el lector puede reconstruir la hoja sin más archivos.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, replace

LETRAS = "ABCDEFGH"
PAPEL = {"carta": (215.9, 279.4), "a4": (210.0, 297.0)}
PREFIJO_QR = "BRB1"


@dataclass(frozen=True)
class Spec:
    """Lo que define la geometría de una hoja."""
    preguntas: int
    opciones: int = 4
    digitos_id: int = 8
    versiones: int = 0          # 0 = examen de una sola versión
    version: str = "-"          # "-" sin versiones, "?" el alumno la rellena, "A".. preimpresa
    papel: str = "carta"
    examen: str = "EXAMEN"

    def validar(self) -> "Spec":
        if not 1 <= self.preguntas <= 200:
            raise ValueError("preguntas debe estar entre 1 y 200")
        if not 2 <= self.opciones <= len(LETRAS):
            raise ValueError(f"opciones debe estar entre 2 y {len(LETRAS)}")
        if not 0 <= self.digitos_id <= 12:
            raise ValueError("digitos_matricula debe estar entre 0 y 12")
        if not 0 <= self.versiones <= 6 or self.versiones == 1:
            raise ValueError("versiones debe ser 0 (una sola) o entre 2 y 6")
        if self.papel not in PAPEL:
            raise ValueError(f"papel debe ser uno de {list(PAPEL)}")
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,24}", self.examen):
            raise ValueError("el id del examen sólo admite letras, números, punto, guion y guion bajo (máx. 24)")
        ok = {"-"} if self.versiones == 0 else {"?", *LETRAS[: self.versiones]}
        if self.version not in ok:
            raise ValueError(f"versión {self.version!r} no válida para {self.versiones} versiones")
        return self

    @property
    def letras(self) -> str:
        return LETRAS[: self.opciones]

    @property
    def letras_version(self) -> str:
        return LETRAS[: self.versiones]

    # ---- QR ----
    def a_qr(self) -> str:
        return (f"{PREFIJO_QR};e={self.examen};v={self.version};q={self.preguntas};"
                f"o={self.opciones};d={self.digitos_id};n={self.versiones};p={self.papel}")

    @staticmethod
    def de_qr(texto: str) -> "Spec":
        partes = texto.strip().split(";")
        if not partes or partes[0] != PREFIJO_QR:
            raise ValueError("el QR no es de una hoja de burbujas")
        kv = dict(p.split("=", 1) for p in partes[1:] if "=" in p)
        return Spec(preguntas=int(kv["q"]), opciones=int(kv["o"]), digitos_id=int(kv["d"]),
                    versiones=int(kv["n"]), version=kv["v"], papel=kv["p"],
                    examen=kv["e"]).validar()


@dataclass(frozen=True)
class Config:
    """El archivo examen.toml completo: la geometría más los textos que se imprimen."""
    base: Spec
    titulo: str = ""
    curso: str = ""
    prefijo_id: str = ""
    etiqueta_id: str = "Matrícula"
    version_preimpresa: bool = True
    instrucciones: str = ("Usa lápiz o pluma oscura y rellena el círculo completo. "
                          "Una sola respuesta por pregunta. Para cambiarla, borra por completo.")

    def specs(self) -> list[Spec]:
        """Una hoja por versión si la versión va preimpresa; si no, una hoja genérica."""
        b = self.base
        if b.versiones == 0:
            return [replace(b, version="-").validar()]
        if self.version_preimpresa:
            return [replace(b, version=L).validar() for L in b.letras_version]
        return [replace(b, version="?").validar()]


def leer_config(ruta: str) -> Config:
    with open(ruta, "rb") as f:
        d = tomllib.load(f)
    ex, hoja = d.get("examen", {}), d.get("hoja", {})
    vers = hoja.get("versiones", [])
    if isinstance(vers, int):
        nver = vers
    else:
        nver = len(vers)
        if vers and "".join(vers) != LETRAS[:nver]:
            raise ValueError(f"las versiones deben ser consecutivas desde A, por ejemplo {list(LETRAS[:nver])}")
    nver = 0 if nver == 1 else nver
    base = Spec(preguntas=int(hoja["preguntas"]), opciones=int(hoja.get("opciones", 4)),
                digitos_id=int(hoja.get("digitos_matricula", 8)), versiones=nver,
                version="-" if nver == 0 else "?", papel=hoja.get("papel", "carta"),
                examen=str(ex.get("id", "EXAMEN")))
    base.validar()
    kw = dict(base=base, titulo=ex.get("titulo", ""), curso=ex.get("curso", ""),
              prefijo_id=hoja.get("prefijo_matricula", ""),
              etiqueta_id=hoja.get("etiqueta_matricula", "Matrícula"),
              version_preimpresa=bool(hoja.get("version_preimpresa", True)))
    if "instrucciones" in hoja:
        kw["instrucciones"] = hoja["instrucciones"]
    return Config(**kw)
