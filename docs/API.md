# API v0.1

Con el servidor en marcha, abre `http://127.0.0.1:8765/docs` para ver el contrato interactivo.

| Método y ruta | Función |
|---|---|
| GET `/api/health` | Estado, límites e indicador de configuración de IA |
| GET/POST `/api/projects` | Listar/crear proyectos |
| GET `/api/project-summaries` | Resumen del inicio por proyecto: tablas, derivados, dashboards y actividad; solo metadatos SQLite |
| GET `/api/projects/{id}/datasets` | Tablas importadas y derivadas |
| POST `/api/projects/{id}/uploads` | Importar un archivo multipart; devuelve job (202) |
| GET `/api/projects/{id}/datasets/{dataset}/preview` | Paginación: `limit` hasta 200, `offset` |
| POST `/api/projects/{id}/runs` | Ejecutar un Plan sobre una tabla (202) |
| GET `/api/projects/{id}/jobs` | Historial de trabajos |
| GET `/api/jobs/{job}` | Estado de una ejecución |
| POST `/api/jobs/{job}/cancel` | Cancelar un trabajo activo |
| POST `/api/projects/{id}/sample-consents` | Preparar muestra local, visible antes del envío |
| POST `/api/projects/{id}/interpret` | Obtener un plan mediante IA; no ejecutarlo |
| POST `/api/projects/{id}/datasets/{dataset}/chart` | Compatibilidad síncrona para tablas ≤100.000 filas; misma definición estadística |
| GET/POST `/api/projects/{id}/dashboards` | Listar/guardar dashboards |
| POST `/api/projects/{id}/datasets/{dataset}/exports` | Generar HTML independiente |
| GET `/api/exports/{export}` | Descargar HTML como adjunto |
| GET `/api/projects/{id}/datasets/{dataset}/download` | Descargar Parquet preparado |
| GET `/api/projects/{id}/datasets/{dataset}/recipe` | Consultar plan, padre e historial |
| GET `/api/projects/{id}/audit` | Actividad reciente |

## Ejemplo de ejecución

```json
{
  "dataset_id": "ID_DEVUELTO_POR_IMPORTACION",
  "plan": {
    "name": "Ventas por región",
    "steps": [
      {"op": "deduplicate"},
      {"op": "aggregate", "columns": ["region"], "metrics": [
        {"column": "ingreso", "function": "sum", "alias": "total"}
      ]}
    ],
    "charts": [{"kind": "bar", "x": "region", "y": "total"}],
    "questions": []
  }
}
```

La respuesta de ejecución contiene un `id` de trabajo. Consulta `/api/jobs/{id}` hasta
que su estado sea `succeeded`, `failed`, `cancelled` o `interrupted`.
Si termina correctamente, `result_id` identifica una tabla nueva.

## Operaciones del Plan

| Operación | Parámetros esenciales | Comportamiento |
|---|---|---|
| select | columns | Selecciona columnas diferentes |
| filter | column, operator, value | Filtra por condición; is_null/not_null no requieren valor |
| deduplicate | Sin columns | Elimina filas totalmente iguales |
| drop_nulls | columns | Descarta filas con nulos en cualquiera de esas columnas |
| fill_null | column, value | Sustituye nulos; el tipo debe ser compatible |
| cast | column, target_type | Conversión estricta; falla si no puede convertir |
| rename | column, alias | Renombra sin sobrescribir otra columna |
| join | dataset_id, left_key, right_key, how | Left/inner; bloquea duplicados de clave derecha por defecto |
| concat | dataset_id | Apila filas; exige mismas columnas y orden; DuckDB resuelve tipos compatibles |
| aggregate | columns, metrics | Agrupa y calcula sum/avg/min/max/count |
| date_part | column, part, alias | Extrae year/month/day/quarter/week/dow |
| ratio | column, denominator, alias | Cociente; denominador cero o nulo devuelve NULL |
| sort | columns, descending | Ordena; nulos al final |

No se acepta SQL libre, Python libre, rutas de archivos ni llamadas a herramientas desde el Plan.
El editor JSON admite los mismos contratos que la IA y que los controles visuales.

## Exploración: trabajos y diccionario

| Método y ruta | Función |
|---|---|
| GET/POST `/api/projects/{id}/datasets/{dataset}/dictionary` | Consultar o editar columnas del diccionario local; aumenta revisión y conserva historial |
| POST `/api/projects/{id}/datasets/{dataset}/analyses` | Cálculo estadístico cancelable (202): chart, quality, categories o export |
| GET `/api/projects/{id}/datasets/{dataset}/categories?column=nombre` | Frecuencias del perfil guardado, hasta 20; no lanza consulta costosa |
| POST `/api/projects/{id}/open` | Abrir proyecto y recuperar borrador |
| POST `/api/projects/{id}/close` | Guardar estado y volver a inicio; rechaza tareas pendientes |
| POST `/api/shutdown` | Cerrar trabajo del programa; rechaza proyectos abiertos/tareas; queda escucha para reiniciar |
| POST `/api/restart` | Reactivar el programa cerrado sin perder proyectos |

Ejemplo de comparación dentro de cada grupo:

```json
{
  "kind": "chart",
  "chart": {
    "kind": "bar", "x": "respuesta", "group": "grupo", "aggregation": "count",
    "measure": "percentage", "denominator": "group", "missing": "exclude",
    "bar_mode": "group", "filters": [{"column": "edad", "operator": "ge", "value": 18}]
  }
}
```

Consulta `/api/jobs/{job}`: en `succeeded`, `result` contiene el gráfico, perfil,
categorías o `download_url`. El campo `result_id` sigue identificando datasets en
importaciones y pipelines. La cancelación es `/api/jobs/{job}/cancel`; un resultado
cancelado o con diccionario cambiado no se publica ni entra en caché.

Otros cuerpos de `/analyses` (solo un bloque de parámetros por solicitud):

```json
{"kind":"quality","quality":{"duplicate_keys":["id"],"exact_quantiles":false}}
```

```json
{"kind":"categories","category_column":"region"}
```

```json
{"kind":"export","export":{"charts":[{"kind":"bar","x":"region","aggregation":"count"}],"title":"Distribución","filter_columns":["region"],"limit":5000}}
```

El diccionario acepta `{"columns":{"nombre":{...}}}` con `semantic_type` obligatorio:
`continuous`, `discrete`, `nominal`, `ordinal`, `binary`, `date`, `identifier`.
Opcionales: `description`, `unit`, `labels` (código textual → etiqueta),
`expected_categories`, `minimum`, `maximum`, `nullable`, `is_target`,
`target_meaning`, `provenance`. El objetivo requiere significado explícito.
GET devuelve sugerencias, linaje, revisión e historial. Los cambios ocultan en la UI
estadísticas semánticas desactualizadas hasta recalcular el perfil.

## Contrato estadístico de gráficos

Se conservan `kind`, `x`, `y`, `title` y todos los planes/dashboards anteriores.
`aggregation=null` con `y` en bar/line conserva valores precomputados; señala cualquier
vista parcial y no afirma que sea una distribución completa. Los nuevos controles
usan agregación explícita. Histogramas antiguos ahora calculan intervalos completos.

| Campo | Definición |
|---|---|
| kind | bar, line, histogram, scatter, box, correlation |
| group | Categoría de comparación; barras agrupadas/apiladas y tablas cruzadas de frecuencias |
| aggregation | count (filas), sum, avg, min, max, median; null conserva Y precomputada |
| measure | count (frecuencia/valor agregado), percentage (solo frecuencias) |
| denominator | used: filas válidas usadas; filtered: todas las filtradas, incluidos excluidos; group: usadas dentro de cada grupo |
| missing | include: categorías NULL; exclude: elimina filas con ausentes en variables usadas; los valores numéricos no finitos nunca se calculan como magnitudes |
| filters | Hasta 10 filtros validados: column, operator, value; no SQL libre |
| order | x, value, value_desc; líneas ordenadas por X de forma predeterminada |
| bar_mode | group o stack |
| bins, bin_start, bin_end | 2–100 intervalos comunes; límites globales o explícitos; [inicio,fin), último cerrado |
| sample_size, seed | Top-k hash de posición monohilo, hasta 5.000 puntos en aplicación; semilla predeterminada 42 |
| columns | Hasta 12 variables para Pearson; excluye nominales, ordinales, binarias e identificadores por defecto |
| category_limit | Hasta 200 resultados de barras o grupos box; predeterminado 100; supera límite → error, nunca porcentaje parcial |
| x_label, y_label, x_unit, y_unit | Etiquetas y unidades editables; unidades del diccionario si no se especifican |

Cada respuesta incluye `figure` (datos/layout Plotly compartidos con HTML), `rows`
(resultados acotados), `warnings`, `scope` y `provenance`: identidad/versionado del
dataset, revisión del diccionario, filtros, población definida, filas totales/filtradas/usadas,
método, denominadores, muestreo, versión del cálculo/DuckDB y fecha.

Box: cuartiles exactos `quantile_cont`, interpolación tipo 7; bigotes = extremos
observados dentro de Q1−1,5 IQR y Q3+1,5 IQR; los atípicos se cuentan sin incluir
observaciones individuales. Pearson: pares finitos por celda; constante o menos de
dos pares → NULL. No se calculan causalidad, significación estadística ni predicción.

Perfil: conteos y frecuencias exactos; cardinalidad HyperLogLog aproximada; cuartiles
T-Digest aproximados salvo petición exacta. Desviación estándar muestral n−1.
Duplicados = filas excedentes respecto a combinaciones distintas, incluyendo NULL.
Reglas por columna cuentan filas incumplidoras una sola vez aunque violen varias reglas.

## Exportación estadística offline

Las agregaciones se calculan sobre todas las filas filtradas y se exportan como resultados,
independientemente de `limit` (que solo acota observaciones precomputadas/muestras).
Las figuras y su definición coinciden con la aplicación. No se incluyen datos individuales
en barras agregadas, histogramas, box plots o Pearson.

Los filtros agregados se desactivan y se explica su alcance: instantánea con filtros de
cálculo fijados, sin recálculo de porcentajes offline. Solo en dashboards compuestos
por bar/line con Y precomputada pueden seleccionarse localmente columnas incluidas.
Si falta una columna de filtro, queda desactivada. Cada gráfico conserva procedencia,
denominadores, método, fecha, avisos y límites. Plotly se incluye; no necesita red.

Los endpoints síncronos antiguos de chart/export rechazan datasets mayores de 100.000
filas y remiten a `/analyses`. Guardar dashboard valida referencias y persiste el
contrato; no vuelve a ejecutar cálculos costosos. La caché incorpora dataset/versionado,
revisión del diccionario, filtros/parámetros y versiones del cálculo y DuckDB.

## Autorización de muestras

`sample-consents` recibe `dataset_ids`, `columns` y `rows` (máximo 10).
Devuelve las filas exactas que se mostrarán y un identificador temporal.
La creación de la muestra no la transmite. El envío se produce únicamente al
incluir ese `consent_id` en `interpret`. El consentimiento dura 10 minutos y se
consume antes de la petición externa, incluso si falla la conexión.

La interfaz usa 5 filas y una tabla por autorización. La API permite varias tablas
si todas contienen las columnas elegidas. Las muestras quedan guardadas localmente
en SQLite como parte de la autorización; no son anónimas por defecto.
