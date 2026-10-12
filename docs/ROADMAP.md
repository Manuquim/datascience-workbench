# Evolución prevista

## v0.1 — Implementada

Proyectos locales, importación CSV/Parquet/JSON/JSONL/NDJSON/XLSX,
normalización Parquet, calidad básica, transformaciones tipadas, ejecución en procesos,
IA como intérprete de planes, consentimiento por envío de muestras,
gráficos, dashboards guardados, exportación HTML offline, descarga Parquet y auditoría.
La actualización de exploración añade diccionario semántico, reglas, duplicados por
claves, IQR, gráficos agregados completos, denominadores, Pearson, muestreo reproducible,
caché y exportación estadística con filtros de alcance explícito.

## Siguiente entrega — Fiabilidad de datos y experiencia

- Tests y benchmarks con datasets reales de varios GB en el equipo del usuario.
- Opciones de delimitador, encoding, formatos de fecha, decimal y selección de hojas Excel.
- Mejoras de sugerencias semánticas y reglas de negocio más expresivas, con revisión humana.
- Perfilado incremental y cuotas de caché/disco para proyectos extensos.
- Editor visual con esquema de salida por paso y vista previa acotada antes de ejecutar.
- Reutilización explícita de recetas, historial de versiones y linaje entre varias tablas.
- Guardado automático de borradores de dashboard y configuración de gráficos.
- Cuotas de disco por proyecto, gestión de archivos fallidos, eliminación y copia de seguridad desde UI.
- Métricas de recursos y presupuesto de llamadas IA en la interfaz.

## Servidor y varios usuarios

Antes de abrir a la red: autenticación, autorización real por usuario/proyecto, HTTPS,
protección de sesiones, límites por usuario y separación de almacenamiento.

Sustituir el repositorio SQLite por uno basado en PostgreSQL si la concurrencia lo exige.
Añadir almacenamiento de objetos y una cola duradera. Evaluar un worker central o
workers aislados por proyecto; no compartir un archivo DuckDB escribible entre procesos.
La v0.1 está deliberadamente vinculada a loopback y rechaza hosts/orígenes externos.

## Agentes y MCP

Usar las operaciones permitidas del Plan como frontera de herramientas.
Añadir MCP cuando se necesiten clientes externos; diseñar identidad, autorización,
consentimiento de muestras y límites también en esa entrada.

El harness actual tiene un único ciclo proponer → validar → revisar → ejecutar.
Una ampliación a varios ciclos deberá acotar llamadas, coste, tiempo, recuperación,
memoria y herramientas. Evaluar Hermes u otro framework mediante una tarea concreta,
con licencia y contrato verificados entonces. No están integrados en la v0.1.

## Modelado — Módulo futuro

El módulo `modeling/` contiene el contrato previsto, sin modelos ejecutables todavía.

Antes de entrenar: fijar objetivo/target, tipo de tarea, partición temporal o por entidad,
baseline, métricas, transformaciones que se ajustan solo con training, trazabilidad,
registro de artefactos y criterios de despliegue. Evitar fuga de información.

Después: inferencia por API, monitorización de entradas y evaluación con etiquetas reales.
Cambios en la distribución no se presentarán como pérdida demostrada de precisión.
