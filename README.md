# burbujas

Hojas de respuestas con burbujas para exámenes de opción múltiple. Generas la hoja en PDF, la imprimes, tus alumnos la rellenan, la escaneas en la copiadora y obtienes las calificaciones en un CSV. La lectura usa sólo visión por computadora clásica, sin inteligencia artificial: cada decisión sigue reglas fijas y se puede revisar.

Las preguntas del examen las escribes donde quieras (Word, Google Docs, LaTeX). La hoja de burbujas va aparte, y por eso nunca se descuadra.

## La herramienta web

La forma más fácil de usarlo es la página web: no hay que instalar nada. Tiene tres pasos (crear la hoja, capturar las respuestas correctas y calificar) y todo el trabajo ocurre dentro del navegador, así que los escaneos con nombres y matrículas nunca salen de la computadora del profe. Las lecturas dudosas se corrigen con un clic sobre la burbuja y las calificaciones se descargan en un CSV que abre en Excel.

Por dentro, la página corre el mismo código de Python de este repositorio gracias a Pyodide. La primera vez descarga el motor (unas decenas de MB) y después queda guardado en el navegador.

Para probarla en tu computadora:

```
python scripts/armar_web.py
cd sitio && python -m http.server 8000
```

y abre http://localhost:8000.

## Instalación para usarlo desde la terminal

Necesitas Python 3.11 o más reciente.

```
pip install git+https://github.com/diegoacanales/burbujas
```

No hace falta instalar LaTeX.

## El flujo, en cuatro pasos

1. Crea los archivos de ejemplo en una carpeta nueva:

   ```
   burbujas ejemplo
   ```

   Aparecen `examen.toml` (cómo es la hoja) y `clave.csv` (las respuestas correctas).

2. Edita `examen.toml` con cualquier editor de texto: número de preguntas, opciones por pregunta, dígitos de matrícula y versiones. Luego genera la hoja:

   ```
   burbujas hoja examen.toml
   ```

   Sale un PDF con una página por versión. Cada hoja trae impresa su versión, con la burbuja ya rellena, y un código QR que le dice al lector cómo es la hoja. Si prefieres una sola hoja para todos y que cada alumno rellene su versión, pon `version_preimpresa = false`.

3. Imprime, aplica el examen y escanea todas las hojas en un solo PDF. Cualquier copiadora sirve; 200 ppp en escala de grises o color es suficiente. También funcionan fotos con el celular, siempre que se vean completos los cuatro cuadros negros de las esquinas.

4. Llena `clave.csv` y califica:

   ```
   burbujas calificar escaneo.pdf --clave clave.csv --config examen.toml
   ```

   En la carpeta `resultados/` quedan:

   - `resultados.csv`: una fila por hoja con matrícula, versión, respuestas leídas, aciertos, puntos y una columna "revisar" con el motivo, si lo hay.
   - `revisar/`: una imagen por hoja con lo que leyó el programa. Verde es acierto, rojo es error, el círculo azul indica la respuesta correcta y el recuadro naranja señala lo que conviene mirar a mano.
   - `analisis_reactivos.csv`: por pregunta, el porcentaje de aciertos y cuántos eligieron cada opción. Sirve para detectar preguntas ambiguas o mal planteadas.

Antes del examen real puedes ensayar todo con hojas rellenadas por computadora:

```
burbujas simular hoja_PARCIAL1.pdf -n 30 --dificil
```

## La clave

El formato más simple es una fila por versión:

```
version,clave
A,CABDACBD
B,DACBBCAD
```

Si una pregunta acepta dos respuestas, o la quieres anular, o las preguntas valen distinto, usa una columna por pregunta. "A|C" acepta las dos, "*" da el punto a todos y la fila "puntos" es opcional:

```
version,1,2,3,4
A,C,A|C,*,D
puntos,1,2,1,1
```

Los dos formatos se pueden guardar desde Excel o Google Sheets como CSV.

## Qué hace el programa cuando algo no está claro

Nunca adivina. Si una pregunta tiene dos burbujas rellenas, una marca muy tenue o restos de un borrón, la respuesta se registra como dudosa y la hoja aparece con "sí" en la columna "revisar". Lo mismo pasa con una matrícula incompleta o repetida en dos hojas. Una pregunta con dos marcas cuenta como incorrecta hasta que la revises.

Para corregir una lectura, abre `resultados/correcciones.csv` y agrega una línea por cambio:

```
archivo,pagina,campo,valor
escaneo.pdf,7,12,B
escaneo.pdf,9,matricula,01234567
```

El campo puede ser el número de pregunta, `matricula` o `version`. Vuelve a correr el mismo comando de `calificar` y los cambios quedan aplicados, con la nota "corregido a mano".

## Cómo lee las hojas

1. Busca los cuatro cuadros negros de las esquinas y endereza la imagen.
2. Usa la barra negra de arriba a la izquierda para saber si la hoja está al revés.
3. Lee el código QR, que trae el número de preguntas, opciones, dígitos y versión. Si el QR no se lee, usa `examen.toml`.
4. Mide cuánta tinta hay dentro de cada burbuja. Toma el canal de color más oscuro, así que la pluma azul o roja cuenta igual que el lápiz.
5. Calcula los umbrales con la propia hoja: compara el nivel de una burbuja vacía con el de una rellena en esa misma hoja. Así se ajusta solo a lápices claros o escaneos oscuros.

## Límites

En una hoja tamaño carta caben 80 preguntas de 4 opciones con 8 dígitos de matrícula y versiones, 104 si no hay matrícula ni versiones, y 66 si son de 5 opciones. Si no caben, el programa avisa. Admite de 2 a 8 opciones, hasta 12 dígitos de matrícula y hasta 6 versiones, en papel carta o A4.

## Consejos para el día del examen

- Muestra la hoja a tus alumnos antes del examen, para que el formato no los tome por sorpresa.
- Pide que no escriban ni doblen cerca de los cuadros negros.
- Si la versión va preimpresa, reparte cada hoja junto con el cuadernillo de la misma letra.

## Estado

Versión 0.1. Probado con hojas simuladas: escaneos limpios, fotos chuecas, sombras, hojas al revés, pluma de color, rellenos incompletos, dobles marcas y borrones. Falta probarlo con hojas impresas y rellenadas a mano.
