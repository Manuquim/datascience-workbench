# Data Science Workbench

Plataforma local en Python y React/TypeScript para preparar, analizar y visualizar
uno o varios archivos por proyecto. Incluye un intérprete de instrucciones mediante
IA externa, revisión del plan, procesos de trabajo separados y dashboards HTML offline.

**Empieza por `QUE_HACE_Y_COMO_FUNCIONA.md`** si quieres entender qué hace el programa
y cómo está resuelto dentro de la estructura del proyecto.

## Arranque en Windows

Requisitos: Windows con Python 3.11–3.14 de 64 bits y acceso a internet para instalar
las dependencias. La validación de esta entrega se realizó con Python 3.12 en Linux.
Se recomienda Python 3.12 para reproducir ese entorno. La aplicación no necesita WSL.

1. Extrae el ZIP completo en una carpeta, por ejemplo `C:\Proyectos\datascience-workbench`.
2. Ejecuta `setup_windows.cmd`. Crea `.venv`, instala las versiones fijadas y crea `.env`.
3. Ejecuta `start_windows.cmd`.
4. Abre **http://127.0.0.1:8765**.
5. Para salir, pulsa **Cerrar proyecto** y después **Cerrar programa** en la pantalla inicial. El proyecto se guarda y puedes abrirlo desde la lista al volver a iniciar. Espera a que terminen las tareas o cancélalas antes de cerrar el proyecto.

El frontend ya está compilado en `frontend/dist/`: **no necesitas instalar Node para usarlo**.
Los scripts usan el Python predeterminado del lanzador `py -3`, o `python` si no existe `py`.
Si tienes varias versiones y quieres una concreta, puedes preparar el entorno manualmente:

```powershell
cd C:\Proyectos\datascience-workbench
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

`Copy-Item` crea la configuración inicial; omítelo si ya tienes un `.env` configurado.
Si el puerto 8765 está ocupado, detén la otra instancia del programa antes de arrancar.

## Linux o WSL

Python 3.11–3.14; si tu distribución separa el paquete `python3-venv`, instálalo previamente.

```bash
cd datascience-workbench
bash setup_linux.sh
.venv/bin/python run.py
```

Abre http://127.0.0.1:8765. En WSL usa preferentemente almacenamiento dentro del filesystem
Linux para los datos de trabajo si buscas mejor rendimiento.

## Configurar la IA

Edita `.env` en la raíz:

```dotenv
OPENAI_API_KEY=tu_clave_de_api
OPENAI_MODEL=modelo_disponible_en_tu_cuenta
```

El modelo debe admitir **Responses y salida estructurada JSON Schema**.
Reinicia el servidor después de cambiar la configuración. El indicador de la interfaz
muestra si hay clave y modelo configurados; no comprueba por sí solo que sean válidos.

Las llamadas a la API tienen su propia facturación. Una suscripción de ChatGPT no
configura ni financia automáticamente la API de esta aplicación.

Sin clave puedes utilizar las transformaciones visuales, el editor JSON y los dashboards.
El adaptador se verificó con un transporte simulado; no se efectuó una llamada facturable
con una clave real en esta entrega.

### Privacidad del contexto

Por defecto se comparten tu instrucción y los identificadores/nombres/tipos de columnas
de hasta 20 tablas del proyecto. No se comparten filas ni nombres de archivos por defecto.

Para compartir una muestra: selecciona columnas, pulsa **Previsualizar muestra**,
revisa las filas y marca la autorización antes de **Preparar plan**. Es un único envío
y el permiso caduca a los diez minutos. Las muestras se conservan en la base local.
No hay anonimización automática; comparte únicamente lo que hayas revisado.

## Primer recorrido sin IA

1. Crea un proyecto llamado «Análisis de ventas».
2. Importa `examples/ventas.csv` y espera a que termine la importación.
3. Revisa «Datos y calidad»: hay un duplicado y algunos valores ausentes.
4. Abre «Pipeline» y despliega «Editar el plan completo · JSON».
5. Pega el contenido de `examples/pipeline-ventas.json`.
6. Pulsa «Ejecutar pipeline» y espera al resultado.
7. Selecciona «Datos y calidad» para comprobar las filas agregadas y pasos aplicados.
8. Abre «Dashboard»: el gráfico previsto en el plan se carga automáticamente.
9. Selecciona `region` como filtro en «Exportación interactiva»; aparecerá el filtro del dashboard.
10. Guarda el dashboard y/o descarga su HTML. Puedes abrirlo sin conexión y sin la aplicación.

El resultado sin duplicados suma:

| Región | Ingreso total | Coste total |
|---|---:|---:|
| Norte | 515 | 315 |
| Sur | 550 | 330 |
| Sin región (NULL) | 80 | 50 |

Puedes importar también `examples/productos.csv` y probar una unión por `producto_id`.
En el pipeline visual elige «Unir tablas» y las claves izquierda/derecha.
La clave derecha debe ser única salvo autorización expresa en JSON.

## Ejemplos de instrucciones a la IA

- «Elimina filas completamente duplicadas y suma ingreso y coste por región. Dibuja ingreso por región».
- «Extrae año y mes de fecha, agrupa por ambos y calcula el ingreso total. Conserva los grupos con datos ausentes».
- «Une la tabla activa con la tabla que tiene categoría por producto_id. Agrupa ingreso por categoría».

La interpretación no ejecuta el plan. Revísalo, resuelve sus preguntas y ejecútalo después.
Para reutilizar un pipeline, selecciona una tabla de entrada y elige una receta del proyecto
en la pestaña «Pipeline».

## Configuración para 16 GB de RAM

Valores iniciales de `.env.example`:

```dotenv
DSW_MEMORY_LIMIT=4GB
DSW_THREADS=2
DSW_TEMP_LIMIT=20GB
DSW_MAX_UPLOAD_GB=10
DSW_JOB_TIMEOUT=1800
```

Un trabajo pesado a la vez. Se permite una consulta de interfaz adicional, por lo que
el presupuesto del motor no es el límite total del programa. DuckDB puede utilizar disco
temporal en operaciones compatibles, pero algunas operaciones siguen necesitando memoria.

Reserva SSD libre para original, subida temporal, Parquet normalizado, intermedios,
resultados y spill. El límite de 20 GB solo limita spill; no limita todo el proyecto.
El límite de 10 GB es de recepción y no garantiza que cualquier operación con ese tamaño
termine correctamente. Las pruebas con datos reales de varios GB en tu equipo quedan pendientes.

Puedes situar los datos fuera del código:

```dotenv
DSW_DATA_DIR=C:/Users/Manuel/DataScienceWorkbench-data
```

## Datos y formatos

- CSV con cabecera y detección automática de tipos/separador; no hay selector de encoding todavía.
- Parquet, recomendado para archivos grandes y resultados.
- JSON tabular, JSONL y NDJSON; no hay editor de aplanamiento de estructuras anidadas.
- XLSX: primera hoja desde la interfaz, o hoja indicada en el campo multipart `sheet` de la API.
  No admite XLS. Las fórmulas necesitan valores calculados previamente.
- XLSX tiene límites adicionales para contenido expandido y metadatos; utiliza CSV/Parquet
  para tablas que excedan esos límites.
- Máximo inicial de 200 columnas por tabla.
- Tablas y dashboards operan sobre datos preparados; la interpretación de unidades y reglas
  de negocio sigue siendo una decisión del análisis.

Las agregaciones, frecuencias y porcentajes se calculan sobre todo el dataset filtrado.
Hasta 8 gráficos y 3 filtros por dashboard; hasta 100 resultados de barras por defecto
(configurable hasta 200), 100 intervalos comunes de histograma y 12 variables para Pearson.
La dispersión muestra hasta 5.000 puntos mediante muestreo reproducible. Los gráficos
antiguos con Y precomputada siguen disponibles y señalan si su vista es parcial.

Los filtros de la aplicación recalculan mediante trabajos cancelables. El HTML incluye
resultados agregados completos, métodos y denominadores; sus filtros estadísticos quedan
fijados. Solo permite seleccionar observaciones precomputadas incluidas cuando puede
hacerlo correctamente. No recalcula estadísticas usando las primeras filas de un archivo.

## Exploración estadística

En **Datos y calidad**, edita el diccionario de cada columna: descripción, unidad, tipo
semántico, códigos/etiquetas, categorías esperadas, rangos, nulos y significado/procedencia
del objetivo opcional. El tipo físico se conserva por separado. Las sugerencias se pueden
corregir; los nombres `id`/`*_id` y códigos reconocidos no se incluyen automáticamente en Pearson.

El perfil muestra valores válidos, ausentes y no finitos; min/max/media/desviación n−1,
mediana, Q1/Q3/IQR cuando la semántica permite esos cálculos. Los cuartiles por defecto
son aproximaciones T-Digest y la cardinalidad es aproximada; las frecuencias del top 20
son exactas sobre la tabla completa. **Recalcular calidad** añade duplicados exactos y por
claves, reglas y la opción de cuartiles exactos tipo 7. Ningún hallazgo elimina filas:
los tratamientos deben añadirse al pipeline y producen un nuevo dataset con informe de cambios.

En **Dashboard**, elige barras simples/agrupadas/apiladas, porcentaje y denominador,
histogramas con intervalos comunes, box plots exactos, dispersión reproducible, Pearson
o líneas con agregación explícita. Puedes editar título, ejes y unidades; el contrato JSON
permite filtros adicionales. Cada gráfico muestra filas usadas, método, filtros y límites.
Son descripciones, comparaciones o asociaciones en este dataset; no prueban causalidad,
no estiman riesgos individuales ni entrenan modelos.

La interfaz utiliza una apariencia técnica con navegación azul oscuro, tablas más
densas y un área de datos a todo el ancho. **Vista ampliada** oculta los proyectos;
**Mostrar proyectos** recupera la navegación. **Asistente IA** abre un panel lateral
plegable que se puede cerrar con Escape. Los gráficos se pueden ver amplios o en
mosaico, y comparten paleta y estilos con el HTML exportado; el color de un grupo
se mantiene al filtrar.

Cuando hay proyectos guardados, el inicio muestra una biblioteca de tarjetas para
abrirlos, sus tablas y dashboards, la actividad registrada y un resumen del espacio
de trabajo. El panel explica el recorrido importar → preparar → explorar → presentar.
Los recuentos usan solo metadatos SQLite, sin volver a leer los archivos de datos.

Los cálculos costosos utilizan la cola existente, cancelación, presupuesto DuckDB y disco
temporal. La caché identifica dataset/versionado, revisión del diccionario, filtros,
parámetros y versión del cálculo. Cambiar el diccionario oculta resultados semánticos
desactualizados hasta recalcularlos. Las nuevas funciones no amplían el contexto enviado
a la IA: estadísticas, gráficos, diccionario y resultados permanecen locales.

Ensayo reproducible de exploración:

```powershell
.venv\Scripts\python.exe scripts/benchmark_exploration.py --rows 1000000 --memory 128MB
```

En Linux: `.venv/bin/python scripts/benchmark_exploration.py --rows 1000000 --memory 128MB`.
Consulta `docs/benchmark-exploration.json` y `docs/VALIDACION.md` para resultados y alcance.
No se ha validado capacidad universal para archivos reales de varios GB.

## Persistencia y copias

Los proyectos y resultados sobreviven al reinicio en `data/` o `DSW_DATA_DIR`.

Para hacer una copia consistente, detén el programa y copia **toda** esa carpeta junto con
las recetas/configuración que quieras conservar. SQLite y Parquet deben mantenerse juntos.
Guarda `.env` por separado si lo necesitas, protegiendo su clave.

No hay borrado de proyectos desde la interfaz en v0.1. Los originales de importaciones
fallidas también se conservan; su gestión se hará en una siguiente entrega.

## Desarrollo y pruebas

Con `uv`:

```bash
uv sync --locked --extra dev
uv run --locked --extra dev pytest -q
uv run --locked --extra dev ruff check backend tests scripts
uv run --locked --extra dev python scripts/benchmark.py
```

Sin `uv`, instala los extras de desarrollo en tu entorno virtual:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check backend tests scripts
python scripts/benchmark.py
```

Para modificar el frontend necesitas Node 22.12+ compatible con Vite:

```bash
cd frontend
npm ci
npm run build
```

El servidor sirve `frontend/dist/`. Tras recompilar, recarga el navegador.
Para desarrollo con recarga automática, ejecuta API y `npm run dev` en consolas separadas;
Vite usa http://127.0.0.1:5173 y redirige `/api` al puerto 8765.

Para el smoke test de interfaz, usa una instancia con datos de prueba:

```bash
cd frontend
npm ci
npx playwright install chromium
npm run test:ui
```

El smoke test crea un proyecto y resultados de demostración. Abre el dashboard descargado
en un contexto offline y comprueba su filtro. No invoca la IA.

## Documentación

- `QUE_HACE_Y_COMO_FUNCIONA.md`: funciones y solución dentro del proyecto.
- `docs/API.md`: contratos y operaciones.
- `docs/VALIDACION.md`: resultados de validación y limitaciones.
- `docs/ROADMAP.md`: siguientes entregas y espacio reservado para modelado, MCP y agentes.

Esta entrega está pensada para uso local individual. La adaptación a servidor necesita
las medidas de autenticación, permisos, almacenamiento y cola recogidas en el roadmap.

En la pantalla final, **Reiniciar programa** vuelve al inicio con los proyectos guardados.
Al cerrar desde la interfaz queda una escucha local para permitir el reinicio; usa Ctrl+C en la consola para terminar completamente el proceso.
