"""Arma la carpeta del sitio: la página (web/) más los módulos de Python que usa el navegador.
Uso: python scripts/armar_web.py [carpeta_destino]   (por omisión, sitio/)"""
import os
import shutil
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULOS = ["__init__.py", "spec.py", "layout.py", "hoja.py", "lector.py", "calificar.py"]

destino = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "sitio")
if os.path.isdir(destino):
    shutil.rmtree(destino)
shutil.copytree(os.path.join(RAIZ, "web"), destino)
os.makedirs(os.path.join(destino, "py", "burbujas"))
for m in MODULOS:
    shutil.copy(os.path.join(RAIZ, "burbujas", m), os.path.join(destino, "py", "burbujas", m))
open(os.path.join(destino, ".nojekyll"), "w").close()
print(f"sitio listo en {destino}")
