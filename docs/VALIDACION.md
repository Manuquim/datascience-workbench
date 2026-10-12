# Validación de la entrega v0.1

## Actualización de exploración estadística — 11 de octubre de 2026

Validada en Windows 11 10.0.26200, Python 3.14.3, DuckDB 1.5.6 y Node 24.
La configuración local del servidor sigue en **8765** y el proxy Vite apunta a ese puerto.
Se conservan los scripts de instalación/inicio Windows y Linux; esta actualización
no se ejecutó en un entorno Linux y no certifica esa combinación.

Se añadieron **20 pruebas de resultados** en `tests/test_exploration.py`, además de
las 32 existentes (incluido cierre/reinicio de proyectos): **52 pruebas superadas**.
Ruff y TypeScript/Vite pasan; ambos recorridos de navegador se ejecutaron en Edge
sin errores JavaScript, con revisión visual de escritorio y móvil. Cubren:

- Grupos A/B con tamaños 100/10: recuentos 60/8 frente a porcentajes 60%/80%.
- Denominadores usados/filtrados/por grupo, nulos y rango de histograma.
- Recuentos y sumas que incluyen 5.050 filas posteriores a las primeras 20.000.
- Histogramas con bordes comunes, intervalos vacíos y columnas constantes.
- Cuartiles exactos tipo 7, bigotes observados y un atípico conocido.
- Pearson sin códigos/identificadores, constantes y número de pares finitos.
- Datos vacíos, NaN/Infinity y muestreo reproducible por semilla.
- Reglas, duplicados completos/por clave y linaje/unidades de agregación.
- Figura estadística idéntica en HTML y aplicación, sin filas individuales agregadas.
- Caché invalidada por filtros/revisión semántica; no publicación tras cancelación.
- Fallo explícito con 4 MB de presupuesto y cancelación de un worker en ejecución
  sobre dos millones de filas y 12 variables.

Comandos de verificación:

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp .qa-verification
python -m ruff check backend tests scripts --no-cache
cd frontend
npm run build
```

El cliente de pruebas Starlette/httpx emite una advertencia de deprecación existente.
Vite mantiene el aviso del tamaño de Plotly incluido para funcionar sin CDN.

### Ensayo reproducible nuevo

`scripts/benchmark_exploration.py --rows 1000000 --memory 128MB`
guarda un reporte opcional con `--output docs/benchmark-exploration.json`.

| Indicador | Observación |
|---|---:|
| Filas / columnas | 1.000.000 / 6 |
| Parquet sintético comprimido | 1.128.319 bytes |
| Presupuesto DuckDB / hilos | 128 MB / 1 |
| Límite de spill | 2 GB |
| Comparación por porcentaje | 1.000.000 filas analizadas, 4 resultados |
| Histograma | 1.000.000 filas, 40 intervalos/grupos |
| Dispersión | 1.000.000 filas válidas, muestra de 1.000 |
| Pearson | 1.000.000 filas, 2 variables compatibles, 4 celdas |

Los tiempos observados y el entorno están en el JSON. No son una promesa de rendimiento;
el Parquet está muy comprimido y el ensayo no mide el RSS total. DuckDB `memory_limit`
limita principalmente su gestor de buffers, no todo el proceso. Los cuartiles exactos,
duplicados de alta cardinalidad y agrupaciones complejas pueden agotar recursos y
fallar de forma explícita. No se han validado archivos reales de varios GB.

### Recorridos de navegador

`scripts/test_project_lifecycle.cjs` comprueba guardado, recarga, restauración, cierre
y reinicio. `scripts/test_exploration_ui.cjs` usa datos locales aislados y comprueba
diccionario, calidad detallada, porcentajes sobre 25.050 filas, filtro que recalcula
las 5.050 filas del grupo posterior, descarga HTML, ejecución offline, igualdad de
figuras y anchura de 390 píxeles. No llama a la IA externa.

### Limitaciones deliberadas

Los filtros de gráficos agregados están fijados/desactivados en HTML: permiten zoom
y selección de series, pero no prometen recalcular nuevas poblaciones sin el backend.
Las únicas selecciones locales admitidas son observaciones precomputadas incluidas.
El perfil usa cuartiles/cardinalidad aproximados etiquetados; los box plots usan cuartiles
exactos. El muestreo es estable para el mismo Parquet, filtros, semilla y versión DuckDB;
no se garantiza la misma selección tras reimportar/reordenar ni representatividad externa.
No hay entrenamiento, causalidad, diagnósticos, inferencia de población ni pruebas de
significación. El diccionario sigue necesitando revisión humana de significados.

---

Los apartados siguientes conservan la validación histórica de la entrega inicial.

Fecha: 11 de octubre de 2026.

## Entorno comprobado

- Linux, Python 3.12.14.
- Entorno virtual aislado con las dependencias de `uv.lock`.
- Node 24.19.0 para compilar el frontend.
- TypeScript y Vite según `frontend/package-lock.json`.
- Navegador Chromium headless mediante Playwright.

Los scripts Windows están incluidos, pero no se ejecutaron sobre un Windows real.
La compatibilidad declarada del proyecto es Python 3.11–3.14; la ejecución probada
corresponde a 3.12. No se certifica el resto de combinaciones por esta prueba.

## Pruebas automatizadas del backend

**31 pruebas pasan** con `python -m pytest -q`.

Cubren importación, perfil básico, paginación, transformaciones, repetición del pipeline,
preservación de originales, conversión fallida sin publicar dataset parcial, uniones
con duplicados, concatenación, aislamiento entre proyectos, rechazo de operaciones
no permitidas, escape de valores, bloqueo de peticiones externas, exportaciones,
persistencia de dashboards, autorización de muestras y contrato del adaptador IA.

Incluyen CSV, Parquet, JSON, JSONL y XLSX. NDJSON utiliza el mismo lector que JSONL.
Comprueban también los totales del ejemplo contra la guía y que una cancelación no
se revierta al iniciar o fallar posteriormente el worker.

La ejecución emite una advertencia de deprecación del cliente de pruebas Starlette/httpx.
No ha producido un fallo funcional. Está acotada al cliente de pruebas utilizado.

## Compilación y revisión estática

- `npm run build`: comprobación TypeScript y construcción Vite correctas.
- `ruff check backend tests scripts`: sin errores.
- Formato Python aplicado con Ruff.

Vite avisa del tamaño del bundle principal, que incluye Plotly completo. Es una decisión
para incluir el gráfico sin depender de CDNs; el bundle puede dividirse u optimizarse
posteriormente. La interfaz compilada se entrega dentro del proyecto.

## Recorrido de interfaz comprobado

El script `scripts/smoke_ui.cjs` realizó:

1. Crear un proyecto.
2. Importar el CSV de ejemplo y esperar su tabla.
3. Editar el Plan JSON y ejecutar el pipeline.
4. Mostrar el gráfico del resultado.
5. Añadir filtro y guardar dashboard.
6. Descargar HTML.
7. Abrirlo desde archivo en un contexto de navegador sin conexión.
8. Aplicar filtro «Norte» y comprobar que queda una fila visible.
9. Comprobar una anchura de 390 píxeles sin desbordamiento horizontal global.
10. Comprobar ausencia de errores JavaScript de página durante el recorrido.

Se revisó visualmente una captura de la interfaz. Las capturas de QA no forman parte
del entregable. El smoke test requiere una instancia local en marcha y crea datos de
prueba; no debe utilizarse como una prueba de solo lectura sobre proyectos reales.

## Ensayo de procesamiento con memoria limitada

Comando: `python scripts/benchmark.py`.

| Indicador | Resultado observado |
|---|---:|
| Filas sintéticas | 2.000.000 |
| Columnas numéricas | 10 |
| Payload lógico mínimo | 160.000.000 bytes |
| Parquet de entrada comprimido | 33.723.507 bytes |
| Presupuesto de memoria DuckDB | 128 MB |
| Máximo de disco temporal informado | 50.593.792 bytes |
| Filas en salida | 2.000.000 |
| Tiempo observado, incluyendo generación | 1,52 segundos |

El ensayo usa la compilación de la operación de ordenación del motor y ejecución
DuckDB directa. Verifica descarga de intermedios a disco en este caso sintético.
No mide el consumo RSS total del proceso ni incluye subida HTTP y toda la interfaz.
Los tiempos dependen del hardware y no son un compromiso de rendimiento.

Durante las pruebas, una ordenación de cadenas largas no terminó con presupuestos
artificialmente pequeños de 32, 64 y 128 MB: DuckDB devolvió falta de memoria.
Esto confirma que el mecanismo de spill no garantiza ejecutar cualquier operación
con cualquier presupuesto. La configuración inicial real de la aplicación es 4 GB.

**No se ha verificado una carga real de varios GB.** El límite de recepción de 10 GB
es configurable y no es una promesa de capacidad universal. La siguiente validación
será con datos y pipelines reales en el ordenador del usuario.

## Alcance de la prueba de IA

El contrato Responses se comprobó con transporte HTTP simulado: payload, modelo
configurado, salida estructurada, `store=false` y validación del Plan.
Se comprobaron además el contexto sin registros, autorización de columnas/filas,
un solo uso y caducidad.

No se realizó una petición con una clave real ni se evaluó la calidad semántica de
un modelo específico. Después de configurar la clave/modelo hay que comprobar una
instrucción sencilla y revisar el plan recibido.

## Trabajo pendiente

Autenticación para servidor, datasets reales de varios GB, cuotas globales de disco,
reglas de calidad de negocio, opciones de importación adicionales, límites de gasto IA,
monitorización de recursos y modelado/MCP/agentes se recogen en `ROADMAP.md`.
