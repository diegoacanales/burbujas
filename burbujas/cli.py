"""Línea de comandos: burbujas ejemplo | hoja | calificar | simular"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))


def cmd_ejemplo(a):
    os.makedirs(a.carpeta, exist_ok=True)
    for f in ("examen.toml", "clave.csv"):
        destino = os.path.join(a.carpeta, f)
        if os.path.exists(destino):
            print(f"ya existe {destino}, no lo toco")
            continue
        shutil.copy(os.path.join(AQUI, "plantillas", f), destino)
        print(f"creado {destino}")
    print("Edita examen.toml y luego corre:  burbujas hoja examen.toml")


def cmd_hoja(a):
    from .hoja import generar, generar_tex
    from .spec import leer_config
    cfg = leer_config(a.config)
    salida = a.salida or os.path.join(os.path.dirname(os.path.abspath(a.config)), f"hoja_{cfg.base.examen}.pdf")
    specs = generar(cfg, salida, copias=a.copias)
    vers = ", ".join(s.version for s in specs if s.version not in "-?") or "una sola hoja"
    print(f"listo: {salida}  ({len(specs) * a.copias} páginas; versiones: {vers})")
    if a.tex:
        tex = os.path.splitext(salida)[0] + ".tex"
        generar_tex(salida, tex)
        print(f"plantilla LaTeX: {tex}")


def cmd_calificar(a):
    from .calificar import calificar
    from .spec import leer_config
    spec, prefijo = None, ""
    if a.config:
        cfg = leer_config(a.config)
        spec, prefijo = cfg.specs()[0], cfg.prefijo_id
    corr = a.correcciones or os.path.join(a.salida, "correcciones.csv")
    print(f"leyendo {len(a.escaneos)} entrada(s)...")
    filas = calificar(a.escaneos, a.clave, a.salida, spec, corr, prefijo)
    n_rev = sum(1 for f in filas if f["revisar"])
    print(f"\n{len(filas)} hojas leídas, {n_rev} para revisar a mano.")
    print(f"resultados:  {os.path.join(a.salida, 'resultados.csv')}")
    print(f"imágenes:    {os.path.join(a.salida, 'revisar')}/")
    if n_rev:
        print("Para corregir una lectura, anótala en correcciones.csv y vuelve a correr el mismo comando.")


def cmd_simular(a):
    from .simular import simular
    salida = a.salida or os.path.splitext(a.hoja)[0] + "_simulado.pdf"
    simular(a.hoja, a.n, salida, semilla=a.semilla, dificil=a.dificil)
    print(f"listo: {salida} ({a.n} hojas rellenadas; lo que se marcó está en *_verdad.json)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="burbujas", description="Hojas de respuestas con burbujas: generar y calificar.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ejemplo", help="crea examen.toml y clave.csv de ejemplo")
    s.add_argument("carpeta", nargs="?", default=".")
    s.set_defaults(f=cmd_ejemplo)

    s = sub.add_parser("hoja", help="genera el PDF de la hoja de respuestas")
    s.add_argument("config", help="archivo examen.toml")
    s.add_argument("-o", "--salida")
    s.add_argument("--copias", type=int, default=1, help="repite el juego de versiones N veces, intercalado")
    s.add_argument("--tex", action="store_true", help="además, una plantilla .tex que inserta la hoja")
    s.set_defaults(f=cmd_hoja)

    s = sub.add_parser("calificar", help="lee los escaneos y califica")
    s.add_argument("escaneos", nargs="+", help="PDF(s), imágenes o carpetas")
    s.add_argument("--clave", required=True, help="clave.csv")
    s.add_argument("--config", help="examen.toml (respaldo si un QR no se lee; también aporta el prefijo de matrícula)")
    s.add_argument("--correcciones", help="CSV con correcciones manuales (por omisión, <salida>/correcciones.csv)")
    s.add_argument("-o", "--salida", default="resultados")
    s.set_defaults(f=cmd_calificar)

    s = sub.add_parser("simular", help="rellena hojas al azar para ensayar el flujo")
    s.add_argument("hoja", help="PDF generado con 'burbujas hoja'")
    s.add_argument("-n", type=int, default=10)
    s.add_argument("-o", "--salida")
    s.add_argument("--semilla", type=int, default=1)
    s.add_argument("--dificil", action="store_true", help="fotos chuecas, sombras, borrones y dobles marcas")
    s.set_defaults(f=cmd_simular)

    a = p.parse_args(argv)
    try:
        a.f(a)
    except (ValueError, FileNotFoundError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
