// Interfaz de Burbujas. El trabajo pesado (generar el PDF y leer las hojas) lo hace
// Python dentro de motor.js; aquí sólo se maneja la página.
import * as pdfjs from "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.min.mjs";
pdfjs.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.min.mjs";

const $ = (s) => document.querySelector(s);
const LETRAS = "ABCDEFGH";
const DPI = 200;
const LADO_MAX = 2600;          // las fotos de celular se reducen a esto: más no mejora la lectura

// ------------------------------------------------------------------ almacenamiento local (opcional)
const guardar = (k, v) => { try { localStorage.setItem("burbujas." + k, JSON.stringify(v)); } catch {} };
const recuperar = (k) => { try { return JSON.parse(localStorage.getItem("burbujas." + k)); } catch { return null; } };

// ------------------------------------------------------------------ motor (Web Worker con Python)
const motor = new Worker("motor.js");
const pendientes = new Map();
let siguienteId = 0;
let motorListo = false;

motor.onmessage = (e) => {
  const m = e.data;
  if (m.tipo === "progreso") { mostrarMotor(m.texto); return; }
  if (m.tipo === "listo") {
    motorListo = true;
    $("#estado-motor").classList.add("listo");
    $("#btn-generar").disabled = false;
    return;
  }
  if (m.tipo === "fallo") {
    mostrarMotor("No se pudo preparar el motor. Revisa tu conexión y recarga la página. Detalle: " + m.texto, true);
    return;
  }
  const p = pendientes.get(m.id);
  if (!p) return;
  pendientes.delete(m.id);
  m.ok ? p.resolver(m.res) : p.rechazar(new Error(m.error));
};

function pedir(accion, datos, transferir = []) {
  return new Promise((resolver, rechazar) => {
    const id = ++siguienteId;
    pendientes.set(id, { resolver, rechazar });
    motor.postMessage({ id, accion, datos }, transferir);
  });
}

function mostrarMotor(texto, fallo = false) {
  const el = $("#estado-motor");
  el.textContent = texto;
  el.classList.toggle("fallo", fallo);
}

// ------------------------------------------------------------------ pestañas
document.querySelectorAll(".pasos button").forEach((b) =>
  b.addEventListener("click", () => irA(b.dataset.paso)));

function irA(paso) {
  document.querySelectorAll(".pasos button").forEach((b) =>
    b.setAttribute("aria-selected", String(b.dataset.paso === paso)));
  document.querySelectorAll(".paso").forEach((s) => s.classList.toggle("activo", s.id === "paso-" + paso));
  if (paso === "clave") dibujarClave();
}

// ------------------------------------------------------------------ 1. hoja
const form = $("#form-hoja");

function slug(s) {
  const t = s.normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 24);
  return t || "EXAMEN";
}

function leerFormulario() {
  const f = form.elements;
  const nv = Number(f.versiones.value);
  return {
    examen: { id: slug(f.titulo.value), titulo: f.titulo.value.trim(), curso: f.curso.value.trim() },
    hoja: {
      preguntas: Number(f.preguntas.value), opciones: Number(f.opciones.value),
      digitos_matricula: Number(f.digitos.value), prefijo_matricula: f.prefijo.value.trim(),
      versiones: nv ? LETRAS.slice(0, nv).split("") : [],
      version_preimpresa: f.preimpresa.value === "1", papel: f.papel.value,
    },
  };
}

function restaurarFormulario() {
  const d = recuperar("formulario");
  if (!d) return;
  for (const [k, v] of Object.entries(d)) {
    const el = form.elements[k];
    if (!el) continue;
    if (el instanceof RadioNodeList) el.value = v; else el.value = v;
  }
}

function guardarFormulario() {
  const f = form.elements, d = {};
  for (const k of ["titulo", "curso", "preguntas", "opciones", "versiones", "digitos", "prefijo", "papel", "preimpresa"])
    d[k] = f[k].value;
  guardar("formulario", d);
}

function actualizarPreimpresa() {
  $("#caja-preimpresa").hidden = form.elements.versiones.value === "0";
}

form.addEventListener("input", () => { guardarFormulario(); actualizarPreimpresa(); });
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!motorListo) return;
  const err = $("#error-hoja");
  err.hidden = true;
  const btn = $("#btn-generar");
  btn.disabled = true;
  btn.textContent = "Generando…";
  try {
    const cfg = leerFormulario();
    const bytes = await pedir("hoja", { config: cfg });
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
    const a = $("#btn-descargar-hoja");
    a.href = url;
    a.download = `hoja_${cfg.examen.id}.pdf`;
    a.hidden = false;
    await vistaPrevia(bytes);
  } catch (ex) {
    err.textContent = traducirError(ex.message);
    err.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generar hoja";
  }
});

function traducirError(msg) {
  const m = /ValueError: (.*)/.exec(msg);
  return m ? m[1] : msg;
}

async function vistaPrevia(bytes) {
  const pdf = await pdfjs.getDocument({ data: bytes.slice() }).promise;
  const pag = await pdf.getPage(1);
  const vp = pag.getViewport({ scale: 1.6 });
  const c = document.createElement("canvas");
  c.width = vp.width; c.height = vp.height;
  await pag.render({ canvasContext: c.getContext("2d"), viewport: vp }).promise;
  const caja = $("#vista-hoja");
  caja.className = "";
  caja.replaceChildren(c);
  if (pdf.numPages > 1) {
    const p = document.createElement("p");
    p.className = "ayuda";
    p.textContent = `El PDF trae ${pdf.numPages} páginas, una por versión. Aquí se muestra la primera.`;
    caja.append(p);
  }
}

// ------------------------------------------------------------------ 2. clave
let claveTextos = recuperar("clave") || {};

function versionesActuales() {
  const n = Number(form.elements.versiones.value);
  return n ? LETRAS.slice(0, n).split("") : ["-"];
}

function dibujarClave() {
  const cfg = leerFormulario();
  const n = cfg.hoja.preguntas, letras = LETRAS.slice(0, cfg.hoja.opciones);
  const cont = $("#tabla-clave");
  cont.replaceChildren();
  for (const v of versionesActuales()) {
    const fila = document.createElement("div");
    fila.className = "fila-clave";
    const et = document.createElement("label");
    et.textContent = v === "-" ? "Clave" : "Versión " + v;
    const inp = document.createElement("input");
    inp.value = claveTextos[v] || "";
    inp.placeholder = letras.slice(0, Math.min(5, letras.length)) + "…";
    inp.dataset.version = v;
    inp.setAttribute("aria-label", et.textContent);
    const cuenta = document.createElement("span");
    cuenta.className = "cuenta";
    const actualizar = () => {
      const limpio = inp.value.toUpperCase().replace(/[^A-H]/g, "");
      const malas = [...limpio].filter((c) => !letras.includes(c));
      cuenta.textContent = `${limpio.length}/${n}`;
      cuenta.className = "cuenta " + (malas.length || limpio.length > n ? "mal" : limpio.length === n ? "ok" : "");
      claveTextos[v] = limpio;
      guardar("clave", claveTextos);
      avisoClave();
    };
    inp.addEventListener("input", actualizar);
    inp.addEventListener("paste", (e) => {
      // pegar varias filas de Excel reparte una por versión
      const txt = e.clipboardData.getData("text");
      const lineas = txt.split(/\r?\n/).map((l) => l.toUpperCase().replace(/[^A-H]/g, "")).filter(Boolean);
      if (lineas.length > 1) {
        e.preventDefault();
        const inputs = [...cont.querySelectorAll("input")];
        const i0 = inputs.indexOf(inp);
        lineas.forEach((l, k) => { if (inputs[i0 + k]) { inputs[i0 + k].value = l; inputs[i0 + k].dispatchEvent(new Event("input")); } });
      }
    });
    fila.append(et, inp, cuenta);
    cont.append(fila);
    actualizar();
  }
  $("#puntos").value = recuperar("puntos") || "";
  $("#anuladas").value = recuperar("anuladas") || "";
}

$("#puntos").addEventListener("input", (e) => { guardar("puntos", e.target.value); avisoClave(); });
$("#anuladas").addEventListener("input", (e) => { guardar("anuladas", e.target.value); avisoClave(); });

function avisoClave() {
  const n = Number(form.elements.preguntas.value);
  const incompletas = versionesActuales().filter((v) => (claveTextos[v] || "").length !== n);
  $("#aviso-clave").textContent = incompletas.length
    ? "Falta completar: " + incompletas.map((v) => (v === "-" ? "la clave" : "versión " + v)).join(", ") + "."
    : "Clave completa.";
  if (lecturas.length) recalcular();
}

function claveCSV() {
  const n = Number(form.elements.preguntas.value);
  const vers = versionesActuales().filter((v) => claveTextos[v]);
  if (!vers.length) return "";
  const anuladas = new Set(($("#anuladas").value.match(/\d+/g) || []).map(Number));
  const filas = [["version", ...Array.from({ length: n }, (_, i) => i + 1)].join(",")];
  for (const v of vers) {
    const t = claveTextos[v];
    filas.push([v, ...Array.from({ length: n }, (_, i) => (anuladas.has(i + 1) ? "*" : t[i] || ""))].join(","));
  }
  const p = ($("#puntos").value.match(/\d+(\.\d+)?/g) || []);
  if (p.length === 1) filas.push(["puntos", ...Array(n).fill(p[0])].join(","));
  else if (p.length > 1) filas.push(["puntos", ...Array.from({ length: n }, (_, i) => p[i] || "1")].join(","));
  return filas.join("\n") + "\n";
}

// ------------------------------------------------------------------ 3. calificar
let lecturas = [];          // lo que devolvió el lector, con las correcciones hechas a mano
let resultados = null;      // filas calificadas que devolvió Python

const zona = $("#zona"), entrada = $("#archivos");
zona.addEventListener("dragover", (e) => { e.preventDefault(); zona.classList.add("encima"); });
zona.addEventListener("dragleave", () => zona.classList.remove("encima"));
zona.addEventListener("drop", (e) => { e.preventDefault(); zona.classList.remove("encima"); procesar([...e.dataTransfer.files]); });
zona.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") entrada.click(); });
entrada.addEventListener("change", () => { procesar([...entrada.files]); entrada.value = ""; });

function progreso(frac, texto) {
  const p = $("#progreso");
  p.hidden = false;
  p.firstElementChild.style.setProperty("--p", Math.round(frac * 100) + "%");
  p.lastElementChild.textContent = texto;
}

function lienzoDesde(fuente, w, h) {
  const k = Math.min(1, LADO_MAX / Math.max(w, h));
  const c = document.createElement("canvas");
  c.width = Math.round(w * k); c.height = Math.round(h * k);
  return c;
}

async function* paginasDe(archivo) {
  if (archivo.type === "application/pdf" || archivo.name.toLowerCase().endsWith(".pdf")) {
    const pdf = await pdfjs.getDocument({ data: new Uint8Array(await archivo.arrayBuffer()) }).promise;
    for (let i = 1; i <= pdf.numPages; i++) {
      const pag = await pdf.getPage(i);
      let vp = pag.getViewport({ scale: DPI / 72 });
      const k = Math.min(1, LADO_MAX / Math.max(vp.width, vp.height));
      vp = pag.getViewport({ scale: (DPI / 72) * k });
      const c = document.createElement("canvas");
      c.width = Math.round(vp.width); c.height = Math.round(vp.height);
      const ctx = c.getContext("2d", { willReadFrequently: true });
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      await pag.render({ canvasContext: ctx, viewport: vp }).promise;
      yield { pagina: i, total: pdf.numPages, datos: ctx.getImageData(0, 0, c.width, c.height) };
    }
  } else {
    const bmp = await createImageBitmap(archivo, { imageOrientation: "from-image" });
    const c = lienzoDesde(bmp, bmp.width, bmp.height);
    const ctx = c.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(bmp, 0, 0, c.width, c.height);
    yield { pagina: 1, total: 1, datos: ctx.getImageData(0, 0, c.width, c.height) };
  }
}

async function procesar(archivos) {
  if (!archivos.length) return;
  if (!motorListo) { progreso(0, "Espera a que termine de prepararse el motor y vuelve a intentarlo."); return; }
  const cfg = JSON.stringify(leerFormulario());
  let hechas = 0;
  for (const a of archivos) {
    try {
      for await (const p of paginasDe(a)) {
        progreso(hechas / (hechas + p.total - p.pagina + 1), `Leyendo ${a.name}, página ${p.pagina} de ${p.total}…`);
        const buf = p.datos.data.buffer;
        const r = await pedir("leer", { buffer: buf, ancho: p.datos.width, alto: p.datos.height,
                                        archivo: a.name, pagina: p.pagina, config: cfg }, [buf]);
        lecturas.push(r);
        hechas++;
        await recalcular();
      }
    } catch (ex) {
      lecturas.push({ archivo: a.name, pagina: 1, error: "no pude abrir el archivo: " + ex.message, respuestas: [], motivos: [] });
      await recalcular();
    }
  }
  progreso(1, `Listo: ${lecturas.length} hojas leídas.`);
}

async function recalcular() {
  const ligeras = lecturas.map(({ archivo, pagina, error, version, matricula, respuestas, motivos, revisada, corregidos }) =>
    ({ archivo, pagina, error, version, matricula, respuestas, motivos, revisada, corregidos: [...(corregidos || [])] }));
  resultados = await pedir("calificar", { lecturas: ligeras, clave: claveCSV(), prefijo: form.elements.prefijo.value.trim() });
  pintarTabla();
}

function pintarTabla() {
  $("#resultados").hidden = false;
  const tb = $("#tabla-res tbody");
  tb.replaceChildren();
  let revisar = 0, suma = 0, nCal = 0;
  resultados.filas.forEach((f, i) => {
    const tr = document.createElement("tr");
    const celdas = [i + 1, f.matricula || "—", f.version || "—",
      f.aciertos === "" ? "—" : `${f.aciertos}/${(f.respuestas || "").length}`,
      f.calificacion === "" || f.calificacion === undefined ? "—" : f.calificacion];
    for (const c of celdas) { const td = document.createElement("td"); td.textContent = c; tr.append(td); }
    const td = document.createElement("td");
    const et = document.createElement("span");
    const err = lecturas[i].error;
    et.className = "etq " + (err ? "err" : f.revisar ? "rev" : "ok");
    et.textContent = err ? "No se pudo leer" : f.revisar ? "Revisar" : "Bien";
    et.title = f.motivos || "";
    td.append(et);
    tr.append(td);
    tr.addEventListener("click", () => abrirRevision(i));
    tb.append(tr);
    if (f.revisar) revisar++;
    if (f.calificacion !== "" && f.calificacion !== undefined) { suma += Number(f.calificacion); nCal++; }
  });
  const sinClave = !claveCSV();
  $("#resumen").textContent = `${resultados.filas.length} hojas` +
    (nCal ? ` · promedio ${(suma / nCal).toFixed(1)} sobre 100` : "") +
    (revisar ? ` · ${revisar} por revisar (clic en la fila)` : "") +
    (sinClave ? " · falta capturar las respuestas correctas en el paso 2" : "");
}

function descargar(texto, nombre) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([texto], { type: "text/csv;charset=utf-8" }));
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
$("#btn-csv").addEventListener("click", () => descargar(resultados.csv, `calificaciones_${slug(form.elements.titulo.value)}.csv`));
$("#btn-analisis").addEventListener("click", () => descargar(resultados.csv_analisis, `analisis_${slug(form.elements.titulo.value)}.csv`));

// ------------------------------------------------------------------ revisión de una hoja
const dlg = $("#revision"), lienzo = $("#lienzo-rev");
let actual = -1;
const imagenes = new Map();

function imagenDe(i) {
  if (!imagenes.has(i)) {
    const im = new Image();
    im.src = lecturas[i].imagen;
    imagenes.set(i, im.decode().then(() => im));
  }
  return imagenes.get(i);
}

async function abrirRevision(i) {
  const r = lecturas[i];
  if (r.error) {
    alert(`${r.archivo}, página ${r.pagina}: ${r.error}.\n\nVuelve a escanearla o captura esa hoja a mano.`);
    return;
  }
  actual = i;
  $("#rev-titulo").textContent = `Hoja ${i + 1}: ${r.archivo}, página ${r.pagina}`;
  $("#rev-matricula").value = r.matricula;
  const sel = $("#rev-version");
  sel.replaceChildren();
  for (const v of (r.versiones && r.versiones.length ? r.versiones.split("") : ["-"]).concat(r.version === "?" ? ["?"] : [])) {
    const o = document.createElement("option");
    o.value = v; o.textContent = v === "-" ? "Única" : v === "?" ? "Sin leer" : v;
    sel.append(o);
  }
  sel.value = r.version;
  await dibujarRevision();
  if (!dlg.open) dlg.showModal();
}

async function dibujarRevision() {
  const r = lecturas[actual], extra = resultados.extra[actual] || {};
  const im = await imagenDe(actual);
  lienzo.width = r.ancho_img; lienzo.height = r.alto_img;
  const ctx = lienzo.getContext("2d");
  ctx.drawImage(im, 0, 0);
  const col = { ok: "#1e8a3c", mal: "#c62f2f", azul: "#1f6fd1", aviso: "#d97a00" };
  const dudosas = new Set(r.motivos.filter((m) => /^P\d+:/.test(m)).map((m) => Number(m.slice(1, m.indexOf(":")))));
  for (let q = 1; q <= r.preguntas; q++) {
    const resp = r.respuestas[q - 1];
    const ok = extra.correctas ? extra.correctas[q - 1] : null;
    for (const l of r.letras) {
      const [x, y] = r.burbujas[q][l];
      const esOk = ok && (ok === "*" || ok.includes(l));
      if (resp === l) circulo(ctx, x, y, r.radio + 2.5, ok ? (esOk ? col.ok : col.mal) : col.azul, 3);
      else if (ok && ok !== "*" && esOk) circulo(ctx, x, y, r.radio + 2.5, col.azul, 1.6);
    }
    if (dudosas.has(q) || resp === "*") {
      const [nx, ny] = r.numeros[q];
      const [ux] = r.burbujas[q][r.letras[r.letras.length - 1]];
      ctx.strokeStyle = col.aviso; ctx.lineWidth = 2.5;
      ctx.strokeRect(nx - 22, ny - r.radio - 5, ux - nx + 22 + r.radio + 8, 2 * r.radio + 10);
    }
  }
  const ul = $("#rev-motivos");
  ul.replaceChildren();
  for (const m of r.motivos) { const li = document.createElement("li"); li.textContent = m; ul.append(li); }
}

function circulo(ctx, x, y, rad, color, ancho) {
  ctx.beginPath(); ctx.arc(x, y, rad, 0, 2 * Math.PI);
  ctx.strokeStyle = color; ctx.lineWidth = ancho; ctx.stroke();
}

lienzo.addEventListener("click", async (e) => {
  const r = lecturas[actual];
  const caja = lienzo.getBoundingClientRect();
  const x = (e.clientX - caja.left) * (lienzo.width / caja.width);
  const y = (e.clientY - caja.top) * (lienzo.height / caja.height);
  let mejor = null;
  for (let q = 1; q <= r.preguntas; q++)
    for (const l of r.letras) {
      const [bx, by] = r.burbujas[q][l];
      const d = Math.hypot(bx - x, by - y);
      if (d < r.radio * 1.8 && (!mejor || d < mejor.d)) mejor = { q, l, d };
    }
  if (!mejor) return;
  r.respuestas[mejor.q - 1] = r.respuestas[mejor.q - 1] === mejor.l ? "" : mejor.l;
  r.motivos = r.motivos.filter((m) => !m.startsWith(`P${mejor.q}:`));
  marcarCorregido(r, `P${mejor.q}`);
  await recalcular();
  await dibujarRevision();
});

function marcarCorregido(r, que) {
  r.corregidos = r.corregidos || new Set();
  r.corregidos.add(que);
}

$("#rev-matricula").addEventListener("change", async (e) => {
  const r = lecturas[actual];
  r.matricula = e.target.value.trim();
  r.motivos = r.motivos.filter((m) => !m.startsWith("matrícula"));
  marcarCorregido(r, "matrícula");
  await recalcular(); await dibujarRevision();
});
$("#rev-version").addEventListener("change", async (e) => {
  const r = lecturas[actual];
  r.version = e.target.value;
  r.motivos = r.motivos.filter((m) => !/versión/.test(m));
  marcarCorregido(r, "versión");
  await recalcular(); await dibujarRevision();
});
$("#rev-ok").addEventListener("click", async () => {
  lecturas[actual].revisada = true;
  await recalcular();
  siguientePorRevisar(1) ?? dlg.close();
});
$("#rev-cerrar").addEventListener("click", () => dlg.close());
$("#rev-sig").addEventListener("click", () => mover(1));
$("#rev-ant").addEventListener("click", () => mover(-1));

function mover(d) {
  const n = lecturas.length;
  for (let k = 1; k <= n; k++) {
    const j = (actual + d * k + n) % n;
    if (!lecturas[j].error) { abrirRevision(j); return; }
  }
}

function siguientePorRevisar(d) {
  const n = lecturas.length;
  for (let k = 1; k < n; k++) {
    const j = (actual + d * k + n) % n;
    if (!lecturas[j].error && resultados.filas[j].revisar) { abrirRevision(j); return j; }
  }
  return null;
}

// ------------------------------------------------------------------ arranque
restaurarFormulario();
actualizarPreimpresa();
