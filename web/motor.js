// Web Worker: carga Python (Pyodide) con OpenCV y el paquete burbujas, y atiende pedidos.
// Corre aparte para que la página no se congele mientras lee los escaneos.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/";
importScripts(PYODIDE + "pyodide.js");

const ARCHIVOS = ["__init__.py", "spec.py", "layout.py", "hoja.py", "lector.py", "calificar.py"];
let py = null;

function avisar(texto) { postMessage({ tipo: "progreso", texto }); }

async function iniciar() {
  avisar("Descargando el motor (sólo la primera vez tarda)…");
  py = await loadPyodide({ indexURL: PYODIDE });
  avisar("Cargando OpenCV y numpy…");
  await py.loadPackage(["numpy", "opencv-python", "pillow", "micropip"]);
  avisar("Instalando el generador de PDF…");
  const micropip = py.pyimport("micropip");
  await micropip.install(["reportlab==5.0.1", "segno==1.6.6"]);
  avisar("Preparando el lector…");
  py.FS.mkdirTree("/home/pyodide/burbujas");
  for (const f of ARCHIVOS) {
    const txt = await (await fetch("py/burbujas/" + f)).text();
    py.FS.writeFile("/home/pyodide/burbujas/" + f, txt);
  }
  py.FS.writeFile("/home/pyodide/api.py", await (await fetch("api.py")).text());
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide'); import api");
}

const listo = iniciar().then(
  () => postMessage({ tipo: "listo" }),
  (e) => postMessage({ tipo: "fallo", texto: String(e) })
);

onmessage = async (ev) => {
  const { id, accion, datos } = ev.data;
  try {
    await listo;
    const api = py.pyimport("api");
    let res;
    if (accion === "hoja") {
      const b = api.hoja_pdf(JSON.stringify(datos.config));
      res = b.toJs(); b.destroy();
      postMessage({ id, ok: true, res }, [res.buffer]);
      return;
    }
    if (accion === "leer") {
      const buf = new Uint8Array(datos.buffer);
      res = JSON.parse(api.leer(buf, datos.ancho, datos.alto, datos.archivo, datos.pagina, datos.config || ""));
    } else if (accion === "calificar") {
      res = JSON.parse(api.calificar(JSON.stringify(datos.lecturas), datos.clave || "", datos.prefijo || ""));
    } else {
      throw new Error("acción desconocida: " + accion);
    }
    postMessage({ id, ok: true, res });
  } catch (e) {
    postMessage({ id, ok: false, error: String(e && e.message ? e.message : e) });
  }
};
