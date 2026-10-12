# Qué hace el programa y cómo lo resuelve

**Proyecto:** Data Science Workbench · **Versión:** 0.1.0

Este archivo relaciona las funciones visibles del programa con los componentes
que las implementan. Describe el código entregado, sus límites y sus puntos de extensión.

## 1. El problema que resuelve

Cuando recibimos uno o varios archivos de datos, las tareas se repiten:
examinar las columnas, encontrar valores ausentes, eliminar duplicados, convertir tipos,
unir tablas, calcular indicadores y presentar resultados.

Hacerlo a mano produce trabajo repetido y dificulta explicar qué transformaciones
originaron una cifra. Cargar archivos grandes enteros en memoria también puede
bloquear un ordenador con 16 GB de RAM.

La aplicación organiza esas tareas en proyectos. Conserva los originales,
normaliza los datos a Parquet, ejecuta planes de transformación y conserva resultados,
recetas y registros de actividad. La interfaz permite inspeccionar tablas y construir
dashboards. Una IA externa puede traducir instrucciones en lenguaje natural a un plan.

La primera versión se centra en preparación, análisis descriptivo y visualización.
No entrena modelos, no ejecuta agentes autónomos de varios ciclos y no integra MCP ni
Hermes. Tiene contratos y documentación para incorporarlos después.

## 2. Qué puede hacer el usuario

1. Crear un proyecto local.
2. Incorporar uno o varios CSV, Parquet, JSON, JSONL, NDJSON o XLSX.
3. Seleccionar una tabla y revisar filas, tipos y valores ausentes.
4. Editar el diccionario semántico y consultar distribuciones, estadísticos, reglas y duplicados.
5. Preparar un pipeline mediante controles visuales, JSON o instrucciones a la IA.
6. Revisar y modificar el plan antes de ejecutarlo.
7. Seguir la ejecución y cancelarla mientras esté en cola o en curso.
8. Revisar el resultado nuevo sin sobrescribir el original.
9. Crear barras simples/agrupadas/apiladas, histogramas comparables, box plots, Pearson, dispersión y líneas agregadas.
10. Aplicar filtros recalculando sobre toda la tabla y guardar dashboards en el proyecto.
11. Exportar un dashboard HTML que funcione sin la aplicación y sin conexión.
12. Descargar los datos preparados en Parquet.
13. Consultar el historial de trabajos, pasos aplicados y actividad.

Los archivos de un proyecto no se unen automáticamente. Debes indicar una unión por
claves o una concatenación. La mera presencia de dos archivos no prueba que tengan
una relación válida.

## 3. Estructura del proyecto

| Archivo o carpeta | Responsabilidad |
|---|---|
| `README.md` | Instalación, arranque y primer recorrido |
| `QUE_HACE_Y_COMO_FUNCIONA.md` | Relación entre funciones, flujo y estructura |
| `pyproject.toml` | Dependencias Python directas y configuración de desarrollo |
| `uv.lock` | Resolución reproducible de dependencias Python |
| `requirements.lock` | Dependencias fijadas con hashes para instalación con pip |
| `.env.example` | Configuración de ejemplo, sin secretos |
| `run.py` | Arranque local de API e interfaz compilada en un mismo origen |
| `setup_windows.cmd` | Crear entorno virtual e instalar dependencias en Windows |
| `start_windows.cmd` | Arrancar el programa en Windows |
| `setup_linux.sh` | Preparación en Linux/WSL |
| `backend/app/config.py` | Rutas, límites de recursos y configuración de la API de IA |
| `backend/app/models.py` | Contratos de entrada: proyectos, planes, pasos, gráficos y muestras |
| `backend/app/main.py` | Rutas HTTP, validación de pertenencia al proyecto y coordinación |
| `backend/app/store.py` | Persistencia SQLite de metadatos y publicación atómica de resultados |
| `backend/app/jobs.py` | Cola local, lanzamiento de procesos, cancelación y timeout |
| `backend/app/worker.py` | Importación o pipeline dentro de un proceso de trabajo |
| `backend/app/engine.py` | Lectura, normalización, estadísticas y operaciones DuckDB |
| `backend/app/metadata.py` | Diccionario semántico, sugerencias corregibles y propagación del linaje |
| `backend/app/statistics.py` | Perfil completo, reglas, duplicados, cálculo estadístico de gráficos y claves de caché |
| `backend/app/chart_style.py` | Paleta técnica compartida, colores estables por grupo/categoría y estilos Plotly |
| `backend/app/ai.py` | Contrato del intérprete y adaptador OpenAI Responses |
| `backend/app/exporter.py` | Dashboard HTML independiente, con datos y biblioteca gráfica incluidos |
| `backend/app/modeling/contracts.py` | Contrato reservado para entrenamiento futuro |
| `frontend/src/main.tsx` | Interfaz React y acciones del usuario |
| `frontend/src/ProjectHome.tsx` | Panel de inicio, biblioteca de proyectos, resumen real y accesos para continuar o crear análisis |
| `frontend/src/Dictionary.tsx` | Editor de metadatos y trabajos de calidad detallada |
| `frontend/src/ChartBuilder.tsx` | Controles de distribución, comparación, asociación y contrato JSON |
| `frontend/src/client.ts` | Peticiones y seguimiento de trabajos cancelables |
| `frontend/src/exploration-types.ts` | Tipos compartidos de diccionario, gráficos y procedencia |
| `frontend/src/style.css` | Diseño visual y adaptación a tamaños de pantalla |
| `frontend/src/technical.css` | Apariencia técnica, área de datos a todo el ancho, vista ampliada y asistente plegable |
| `frontend/dist/` | Interfaz ya compilada para ejecutar sin instalar Node |
| `frontend/package-lock.json` | Dependencias JavaScript fijadas |
| `tests/test_workbench.py` | Pruebas de flujo, operaciones, privacidad y fallos |
| `tests/test_exploration.py` | Resultados estadísticos conocidos, denominadores, semántica, exportación, caché y cancelación |
| `scripts/benchmark.py` | Prueba reproducible de ordenación con memoria limitada |
| `scripts/benchmark_exploration.py` | Ensayo reproducible de exploración con memoria limitada y reporte del entorno |
| `scripts/smoke_ui.cjs` | Recorrido automatizado de interfaz mediante Playwright |
| `examples/` | Archivos y receta de ejemplo para empezar sin datos propios |
| `docs/API.md` | Contratos HTTP y catálogo de transformaciones |
| `docs/ROADMAP.md` | Ampliaciones previstas, incluyendo servidor, agentes, MCP y modelos |
| `docs/VALIDACION.md` | Comprobaciones ejecutadas y alcance de sus resultados |

La implementación es un monolito modular con un worker separado. No hay microservicios.
Los módulos se separan por responsabilidad; no se presenta como una implementación
completa de arquitectura hexagonal. El motor de datos y el repositorio tienen acoplamientos
prácticos que podrían separarse con nuevos adaptadores al crecer el proyecto.

## 4. Relación entre funcionalidades y solución técnica

| Necesidad | Cómo la resuelve | Componentes |
|---|---|---|
| Organizar análisis independientes | Cada recurso pertenece a un proyecto con identificador generado | `main.py`, `store.py`, interfaz React |
| Trabajar con varios archivos | Cada importación crea una tabla; el plan expresa cómo combinarla | `models.py`, `engine.py` |
| Conservar el origen de las cifras | Original guardado, checksum SHA-256, relación padre/resultado y receta | `worker.py`, `store.py` |
| Admitir varios formatos | CSV/JSON/Parquet mediante DuckDB; Excel por lectura secuencial y CSV intermedio | `engine.py`, `worker.py` |
| Unificar tratamiento | Toda importación se materializa como Parquet | `worker.py` |
| Evitar cargar tablas completas en Python | Ejecutar operaciones en DuckDB y entregar páginas o vistas acotadas | `engine.py`, `main.py` |
| Inspeccionar calidad básica | Conteo de filas y nulos; estadísticas de columnas numéricas | `Engine.profile` |
| Repetir limpieza y análisis | Plan tipado almacenado con pasos y parámetros | `models.py`, `worker.py`, `store.py` |
| Evitar transformaciones silenciosas | Conversión estricta y fallo sin publicación de resultado parcial | `engine.py`, `worker.py` |
| Detectar uniones peligrosas | Comprobar duplicados de la clave derecha antes de unir | `Engine.compile_step` |
| Mantener la interfaz utilizable | Ejecutar importaciones y pipelines fuera del proceso de la API | `jobs.py`, `worker.py` |
| Evitar pérdida por cancelación | Cancelación y publicación de resultado en transacciones SQLite | `store.py`, `jobs.py` |
| Interpretar una petición natural | Pedir un Plan estructurado a la API de IA | `ai.py` |
| Acotar la autoridad de la IA | Solo operaciones permitidas; sin SQL/Python/rutas arbitrarias | `models.py`, `main.py`, `engine.py` |
| Compartir muestras de forma explícita | Vista previa local, token de un uso y caducidad de 10 minutos | `main.py`, `ai.py`, interfaz React |
| Construir gráficos | Cálculos DuckDB completos y figuras compartidas con la exportación Plotly | `engine.py`, `frontend/src/main.tsx` |
| Conservar dashboards | Guardar especificaciones y tabla de referencia en SQLite | `main.py`, `store.py` |
| Entregar una presentación autónoma | HTML con JavaScript, datos seleccionados, gráficos y filtros incluidos | `exporter.py` |
| Preparar modelado posterior | Contrato de entrenamiento y decisiones enumeradas en roadmap | `modeling/contracts.py`, `docs/ROADMAP.md` |

## 5. Qué ocurre al importar un archivo

1. La interfaz envía el archivo a la API.
2. La API comprueba proyecto, formato y límites de tamaño.
3. El archivo se guarda con un nombre interno generado en `originals/`.
4. Se registra un trabajo en cola en SQLite.
5. El scheduler arranca un proceso Python para ese trabajo.
6. El worker calcula el SHA-256 del original y lo lee mediante el motor.
7. Si es Excel, lee la primera hoja —o la hoja indicada por API— y genera un CSV intermedio.
8. El motor escribe una versión Parquet.
9. Se calculan tipos, nulos, estadísticas numéricas y una vista previa.
10. La tabla y el éxito del trabajo se publican juntos en una transacción.
11. La interfaz consulta estados periódicamente y muestra la tabla disponible.

La subida por HTTP es multipart con almacenamiento temporal del parser. Aunque el
motor no necesita cargar la tabla completa, la subida requiere disco temporal adicional.
En esta versión no hay subidas reanudables ni conexión directa a una ruta local elegida.

## 6. Qué ocurre al ejecutar un pipeline

El Plan incluye un nombre, una explicación, pasos, gráficos y posibles preguntas.
Si hay preguntas sin resolver, no se permite ejecutarlo.

Cada paso es una operación de un catálogo cerrado: seleccionar, filtrar, deduplicar,
quitar/rellenar nulos, convertir, renombrar, unir, concatenar, agrupar, extraer fecha,
calcular cocientes u ordenar.

El motor comprueba los nombres de columnas y construye la consulta con identificadores
y literales escapados. No concatena SQL libre generado por la IA. El resultado de cada
paso se materializa temporalmente en Parquet. Se registra su número de filas y advertencias.

Al final se calcula el perfil, se comprueban las referencias de los gráficos y se publica
una tabla nueva vinculada a la tabla de entrada. Los Parquet intermedios se eliminan
tras una ejecución correcta. Si falla, no se publica un dataset parcial y se conserva
un diagnóstico local del error.

**Orden y reproducibilidad:** si el análisis depende del orden, el plan debe incluir
una ordenación con claves suficientes para resolver empates. Sin ella, SQL no promete
un orden estable de filas. Repetir parámetros y datos permite reproducir cálculos;
no se promete igualdad binaria de archivos ni orden de filas sin claves explícitas.

## 7. Exploración estadística e intérprete de instrucciones

### Qué resuelve cada función

El diccionario de `metadata.py` distingue almacenamiento y significado. Cada variable
conserva descripción, unidad, tipo semántico, códigos/etiquetas, categorías esperadas,
restricciones y procedencia. El objetivo opcional requiere significado explícito. Las
sugerencias por tipo/nombre son editables; no verifican el significado de los datos.
`store.update_dictionary` conserva revisiones y un historial de cambios en SQLite.
Renombrar conserva la definición; seleccionar elimina solo metadatos de columnas
descartadas; agregar crea métricas nuevas y conserva unidades y linaje de origen;
ratio/date_part crean variables sugeridas para revisar. Join resuelve nombres repetidos
como el motor SQL; concatenar definiciones incompatibles exige revisar significados.
El pipeline conserva dataset padre y revisión del diccionario fuente, así como filas
antes/después y cambios de tamaño por paso.

`statistics.profile` recorre Parquet con DuckDB: nulos y no finitos por separado,
estadísticos solo para variables cuantitativas, cardinalidad aproximada HyperLogLog
y top 20 de frecuencias exactas. La desviación es n−1. Cuartiles predeterminados T-Digest
(aproximados); la calidad detallada puede usar `quantile_cont` exacto tipo 7. El IQR
es Q3−Q1 y marca valores fuera de Q1−1,5 IQR y Q3+1,5 IQR; el conteo es exacto dado
el umbral, que puede provenir de cuartiles aproximados. No elimina observaciones.
Duplicados completos o por claves = filas excedentes frente a combinaciones distintas,
incluyendo NULL. Las reglas opcionales cuentan incumplimientos sin tratar los datos.
Editar semántica marca el perfil como desactualizado; la UI oculta estadísticos afectados
hasta recalcular calidad mediante `Dictionary.tsx`.

`ChartSpec` en `models.py` añade agrupación, agregación, medida, denominador, filtros,
orden, intervalos, ausentes y etiquetas sin romper las especificaciones guardadas.
`statistics.calculate_chart` calcula sobre todas las filas filtradas:

- Barras/frecuencias cruzadas: cuenta o agrega con DuckDB; los porcentajes usan filas
  utilizadas, todas las filtradas o las utilizadas dentro de cada grupo. Las categorías
  no se recortan silenciosamente: superar el límite produce un error que pide filtrar.
- Histogramas: intervalos globales comunes a todos los grupos, incluyendo ceros y
  el extremo superior en el último intervalo. No usa el histograma del navegador.
- Box plots: cuartiles exactos tipo 7; bigotes en los extremos observados dentro de
  las cercas IQR; cuenta atípicos, sin exportar puntos individuales.
- Dispersión: muestra top-k por hash de posición y semilla; lectura monohilo, mismo
  Parquet, filtros y versión DuckDB producen la misma selección. Cambiar reimportación
  u orden puede cambiarla. Se indica tamaño y semilla; no se afirma representatividad.
- Pearson: hasta 12 variables semánticamente cuantitativas, pares finitos por celda,
  número de pares visible; columnas constantes o menos de dos pares dan resultado
  no definido. Excluye identificadores/códigos nominales, ordinales y binarias por defecto.
- Líneas nuevas: tiempo u otro eje cuantitativo ordenado, agregación explícita.
  Los gráficos antiguos con Y precomputada conservan su comportamiento y señalan
  vistas parciales, sin describirlas como distribuciones completas.

Cada resultado devuelve figura, datos acotados, avisos y procedencia: identidad de
dataset, revisión semántica, filtros, filas totales/filtradas/usadas, método, denominadores,
fecha, muestreo y versiones. La UI presenta descripción, comparación y asociación
en este dataset; no ofrece causalidad, diagnósticos, probabilidades individuales ni
extrapolaciones injustificadas. Grupos menores de 20 generan un aviso descriptivo,
no un criterio de significación estadística.

`main.py` ofrece `/analyses` y `worker.py` ejecuta chart/quality/categories/export
en la cola existente (`jobs.py`), con cancelación, timeout y recursos heredados de
la configuración activa. `store.complete_analysis` publica atómicamente resultado,
perfil/caché/exportación; una cancelación o revisión semántica cambiada impide publicarlos.
La caché usa identidad/versionado de dataset, revisión de diccionario, todos los parámetros
y versiones del cálculo y DuckDB. Los originales, recetas y el módulo reservado de
modelado se conservan. No se carga la tabla completa en Pandas ni en el navegador.

La IA continúa proponiendo planes del catálogo validado. Su esquema incluye los nuevos
gráficos; no recibe automáticamente diccionario, estadísticas, gráficos ni resultados.
Si «riesgo» no tiene definición de objetivo local, se devuelve una pregunta antes de
contactar al proveedor. El significado debe explicitarse; la autorización de muestras
conserva su flujo de vista previa, consentimiento, caducidad y un único envío.

### Intérprete de instrucciones y privacidad

La implementación inicial usa OpenAI Responses con salida estructurada y validación
posterior del Plan. Se configura mediante `OPENAI_API_KEY` y `OPENAI_MODEL` en `.env`.
El modelo debe soportar el contrato de salida estructurada utilizado.

Por defecto recibe:

- La instrucción que escribes.
- El identificador de la tabla activa.
- Identificadores y nombres/tipos de columnas de hasta 20 tablas del proyecto.

No se envían nombres de archivos, estadísticas ni registros de datos por defecto.
Los nombres de columnas pueden contener información sensible; siguen siendo información
compartida con el proveedor. También puede ser sensible lo que escribas en tu instrucción.

Si autorizas muestras:

1. Seleccionas columnas y pides una vista previa.
2. El servidor obtiene y guarda localmente las filas exactas de esa muestra.
3. Revisas la muestra en la interfaz.
4. Marcas la autorización para el siguiente envío.
5. Al pedir el plan se envían exclusivamente esas muestras además del contexto habitual.
6. El token se consume antes de la llamada externa y no puede reutilizarse.

La solicitud de IA usa `store=false`. Esto no equivale a una garantía general de retención
cero por parte del proveedor. No se implementa anonimización automática.

La IA no ejecuta el pipeline. Tampoco autoriza uniones con claves derechas duplicadas.
El usuario debe revisar el significado del plan, porque una salida válida según el esquema
puede ser incorrecta para el objetivo de negocio.

La aplicación funciona sin clave: los controles y el editor JSON siguen disponibles.
El adaptador de IA se ha probado con respuestas simuladas; la validación real con tu
cuenta requiere configurar tu clave y el modelo y realizar una solicitud.

## 8. Cómo se distribuye el almacenamiento

Al ejecutar el programa aparece `data/`, o la carpeta indicada en `DSW_DATA_DIR`.

| Ruta creada en ejecución | Contenido |
|---|---|
| `data/metadata.sqlite3` | Proyectos, tablas, planes, dashboards, trabajos, consentimientos y auditoría |
| `data/projects/<id>/originals/` | Archivos originales de importación |
| `data/projects/<id>/runs/<job>/result.parquet` | Tabla normalizada o resultado de pipeline |
| `data/projects/<id>/runs/<job>/error.log` | Diagnóstico de una ejecución fallida, si corresponde |
| `data/projects/<id>/exports/` | Dashboards HTML exportados |
| `data/query-temp/` | Temporales de consultas de vista previa/exportación |

Las claves API no se guardan en SQLite ni llegan al navegador. Las muestras autorizadas
sí quedan en SQLite localmente. Los diagnósticos y datos tratados también pueden contener
información sensible. La protección del disco y las copias de seguridad corresponde al
entorno local; no se implementa cifrado de archivos en esta versión.

## 9. Decisiones para un equipo con 16 GB de RAM

- Un trabajo pesado simultáneo.
- DuckDB configurado por defecto con `memory_limit=4GB` y dos hilos.
- Uso de disco temporal cuando DuckDB puede descargar una operación a disco.
- Límite de 20 GB para el espacio de spill del motor, configurable.
- Hasta 50 filas por página en la interfaz; hasta 200 mediante la API.
- Cálculos agregados sobre todas las filas filtradas, nunca sobre un prefijo de 5.000/20.000 filas.
- Hasta 5.000 puntos de dispersión con muestra reproducible; hasta 100 resultados de barras por defecto, configurable a 200.
- Hasta 100 intervalos comunes de histograma y 12 variables para Pearson.
- Hasta 200 columnas por tabla y 10 GB por archivo como límite de recepción configurable.

`memory_limit` no es un límite duro de RAM de todo el programa. Existen asignaciones
fuera del gestor de buffers; una consulta de interfaz puede coincidir con un worker.
El tamaño del archivo tampoco equivale al tamaño de la operación o de sus intermedios.

El límite temporal del motor no cubre originales, Parquet derivados, intermediarios del
pipeline ni el archivo temporal de la subida. Reserva espacio suficiente en SSD y valida
los pipelines reales. Se incluye un benchmark de ordenación con presupuesto de 128 MB;
no representa una certificación de capacidad para cualquier archivo de varios GB.

## 10. Qué significa un dashboard independiente

El HTML exportado incluye la biblioteca Plotly, las figuras calculadas por el backend
y su procedencia. Los gráficos agregados incluyen resultados estadísticos completos,
no las primeras filas del archivo. No necesita la API, React ni conexión a internet.

Puede hacer zoom, mostrar detalles y seleccionar series. Los filtros de gráficos agregados
quedan fijados en la instantánea y se desactivan con una explicación visible: no se puede
recalcular correctamente sin datos originales/backend. En dashboards antiguos de valores
Y precomputados pueden seleccionarse observaciones incluidas, hasta 200 valores por filtro,
sin afirmar que se recalculan estadísticas del dataset original.

Es una instantánea. No actualiza datos ni procesa nuevamente el dataset original.
Si el resultado supera el límite de exportación, el documento indica que contiene una
vista parcial. Quien recibe el HTML puede inspeccionar los datos incluidos en él.

La aplicación sí recalcula sus filtros sobre toda la tabla a través de trabajos cancelables.
El exportador (`exporter.py`) llama al mismo cálculo (`statistics.calculate_chart`) y usa
los mismos datos/layout Plotly que la aplicación. Incluye filtros, denominadores, tamaño
analizado, método, fecha, límites y avisos. Solo la dispersión requiere observaciones
individuales muestreadas; box plots, correlaciones e histogramas exportan resúmenes.

## 11. Seguridad y fiabilidad presentes

- Arranque en `127.0.0.1`, un único proceso API.
- Validación de host y rechazo de orígenes externos en el navegador.
- Contratos estrictos sin campos desconocidos.
- Comprobación de pertenencia de tablas al proyecto.
- Nombres internos de archivos generados; planes sin acceso a rutas.
- Operaciones limitadas y consultas construidas mediante valores escapados.
- Extensiones DuckDB sin instalación/carga automática.
- Conversión estricta: errores explícitos en datos incompatibles.
- Bloqueo preventivo de uniones con claves derechas duplicadas.
- Publicación atómica de resultado/estado y cancelación sin publicar resultados incompletos.
- Recuperación de trabajos pendientes/en curso como interrumpidos al reiniciar.
- Autorización temporal y de un uso para muestras de IA.
- Tiempo máximo de trabajo configurable.
- Originales conservados y trazabilidad de pasos.

No hay autenticación de usuarios todavía. La comprobación de pertenencia al proyecto
no sustituye una autorización por usuario. Para servir la aplicación en red son necesarias
las mejoras descritas en `docs/ROADMAP.md`; no basta con cambiar la dirección de escucha.

## 12. Límites funcionales actuales

- Calidad básica; no hay reglas de negocio ni detección automática de outliers.
- Duplicados completos se eliminan mediante un paso; no se hace un informe previo automático.
- No se interpretan automáticamente monedas, formatos locales ambiguos ni unidades.
- CSV requiere datos compatibles con el lector y su inferencia; no hay selector de encoding.
- Excel se limita a XLSX; las fórmulas necesitan valores previamente calculados en el archivo.
  El ZIP expandido se limita a 512 MB, las cadenas compartidas a 64 MB y estilos a 8 MB,
  para acotar metadatos que el lector puede cargar en memoria. Para tablas mayores, usa CSV o Parquet.
- Datos JSON anidados pueden conservar tipos complejos, pero las transformaciones iniciales
  están pensadas para columnas tabulares; no existe un editor de aplanamiento.
- Los controles visuales muestran el esquema de la tabla activa, no el esquema simulado
  después de cada paso; para columnas intermedias se usa JSON o la IA.
- Los dashboards manuales deben guardarse explícitamente. No hay autosave de borradores.
- No hay edición/borrado de proyectos ni gestión de cuotas desde la interfaz.
- No hay entrenamiento, inferencia de modelos, alertas programadas ni conectores a otras APIs.
- MCP, Hermes y herramientas autónomas están previstos, no implementados.

## 13. Cómo ampliar el proyecto

Para una operación nueva: actualizar el contrato `Step`, implementar y validar su
compilación en `engine.py`, añadir sus pruebas y, si procede, su control visual.

Para otro proveedor IA: implementar `PlanInterpreter.interpret` y conectarlo a
`create_app`. Conservar validación, consentimiento y límites fuera del proveedor.

Para modelado: implementar `ModelTrainer` y añadir servicios de aplicación que registren
splits, experimentos y artefactos. El dataset preparado es la entrada; el dashboard puede
presentar métricas de modelos sin convertirse en responsable del entrenamiento.

Para servidor: introducir autenticación, autorización, almacenamiento y cola adecuados
antes de abrir acceso externo. Mantener los contratos funcionales del pipeline.

## 14. Documentación técnica consultada

- DuckDB, procesamiento mayor que memoria:
  https://duckdb.org/docs/lts/guides/performance/how_to_tune_workloads.html
- DuckDB, gestión de memoria:
  https://duckdb.org/2024/07/09/memory-management
- Plotly, exportación HTML interactiva:
  https://plotly.com/python/interactive-html-export/
- OpenAI, salidas estructuradas:
  https://developers.openai.com/api/docs/guides/structured-outputs

Las versiones de dependencias verificadas están fijadas en los archivos de bloqueo.
