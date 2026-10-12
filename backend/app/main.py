import json
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .ai import OpenAIInterpreter, consent_valid, expires_at
from .config import ROOT, Settings
from .engine import Engine
from .exporter import export_dashboard
from .jobs import Jobs
from .models import (
    AnalysisRequest,
    ChartSpec,
    DashboardCreate,
    DictionaryUpdate,
    ExportRequest,
    InterpretRequest,
    Plan,
    ProjectCreate,
    RunRequest,
    SampleConsent,
)
from .store import Store, uid
from .metadata import dictionary
from .statistics import calculation_key


class BodyLimitMiddleware:
    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        is_upload = scope["path"].endswith("/uploads")
        limit = self.limit if is_upload else 1024 * 1024
        headers = dict(scope.get("headers", []))
        try:
            too_large = int(headers.get(b"content-length", b"0")) > limit
        except ValueError:
            too_large = True
        if too_large:
            response = JSONResponse(
                {"detail": "El cuerpo supera el límite permitido."}, status_code=413
            )
            return await response(scope, receive, send)
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "El cuerpo supera el límite permitido.")
            return message

        return await self.app(scope, bounded_receive, send)


def create_app(settings=None, interpreter=None):
    settings = settings or Settings.from_env()
    store = Store(settings.data_dir, recover=True)
    jobs = Jobs(store, settings)
    interpreter = interpreter or OpenAIInterpreter(settings)
    session_lock = threading.Lock()
    open_projects = set()
    shutting_down = False
    ai_lock = threading.Lock()
    query_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="Data Science Workbench", version="0.1.0", lifespan=lifespan)
    app.state.store, app.state.jobs = store, jobs
    app.add_middleware(
        BodyLimitMiddleware, limit=int(settings.max_upload_gb * 1024**3) + 1024 * 1024
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {
            "http://localhost:8765",
            "http://127.0.0.1:8765",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        }
        allowed.add(str(request.base_url).rstrip("/"))
        if origin and origin not in allowed:
            return JSONResponse({"detail": "Origen no autorizado."}, status_code=403)
        safe_navigation = (
            request.method == "GET"
            and request.url.path == "/"
            and request.headers.get("sec-fetch-mode") == "navigate"
            and not origin
        )
        if request.headers.get("sec-fetch-site") == "cross-site" and not safe_navigation:
            return JSONResponse({"detail": "Solicitud externa bloqueada."}, status_code=403)
        if (
            shutting_down
            and request.url.path.startswith("/api")
            and request.url.path
            not in ("/api/health", "/api/projects", "/api/restart", "/api/shutdown")
        ):
            return JSONResponse(
                {"detail": "El programa est\u00e1 cerrado. Rein\u00edcialo para continuar."},
                status_code=409,
            )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cache-Control"] = (
            "no-store" if request.url.path.startswith("/api") else "no-cache"
        )
        return response

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse({"detail": str(exc).strip("'")}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    def public_dataset(data):
        return {k: v for k, v in data.items() if k not in ("path", "original_path")}

    def project(ident):
        return store.get("project", ident)

    def query_engine(project_id):
        return Engine(settings, store, project_id, store.root / "query-temp")

    @app.get("/api/health")
    def health():
        return {
            "status": "closed" if shutting_down else "ok",
            "version": "0.1.0",
            "ai_configured": bool(settings.api_key and settings.ai_model),
            "ai_model": settings.ai_model or None,
            "memory_limit": settings.memory_limit,
            "max_upload_gb": settings.max_upload_gb,
            "heavy_job_concurrency": 1,
        }

    @app.get("/api/projects")
    def projects():
        return store.list("project")

    @app.get("/api/project-summaries")
    def project_summaries():
        # Read only compact metadata; never open data files or send previews to the home screen.
        with store.connect() as con:
            rows = con.execute("""
                SELECT project_id,
                    SUM(CASE WHEN kind='dataset' THEN 1 ELSE 0 END) AS datasets,
                    SUM(CASE WHEN kind='dataset' AND json_extract(payload,'$.parent_id') IS NOT NULL THEN 1 ELSE 0 END) AS derived,
                    SUM(CASE WHEN kind='dashboard' THEN 1 ELSE 0 END) AS dashboards,
                    MAX(created_at) AS latest_activity
                FROM records WHERE kind IN ('dataset','dashboard','audit')
                GROUP BY project_id
            """).fetchall()
        return {
            row["project_id"]: {
                key: row[key] for key in ("datasets", "derived", "dashboards", "latest_activity")
            }
            for row in rows
            if row["project_id"]
        }

    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectCreate):
        name = body.name.strip()
        if not name:
            raise ValueError("El proyecto necesita un nombre.")
        return store.put("project", {"name": name, "description": body.description})

    @app.post("/api/projects/{project_id}/open")
    def open_project(project_id: str):
        with session_lock:
            if shutting_down:
                raise HTTPException(409, "El programa se está cerrando.")
            saved = project(project_id)
            open_projects.add(project_id)
            return saved.get("workspace", {})

    @app.post("/api/projects/{project_id}/close")
    def close_project(project_id: str, body: dict):
        with session_lock:
            project(project_id)
            if any(j["status"] in ("queued", "running") for j in store.list("job", project_id)):
                raise HTTPException(
                    409,
                    "Espera a que terminen las tareas o cancélalas antes de cerrar el proyecto.",
                )
            store.update("project", project_id, workspace=body)
            open_projects.discard(project_id)
            return {"saved": True}

    @app.post("/api/shutdown")
    def shutdown(background_tasks: BackgroundTasks):
        nonlocal shutting_down
        with session_lock:
            if shutting_down:
                return {"closed": True}
            if open_projects:
                raise HTTPException(409, "Cierra el proyecto antes de cerrar el programa.")
            if any(j["status"] in ("queued", "running") for j in store.list("job")):
                raise HTTPException(
                    409, "Hay tareas en curso. Espera a que terminen antes de cerrar el programa."
                )
            callback = getattr(app.state, "shutdown_callback", None)
            if callback is None:
                raise HTTPException(
                    409, "Para cerrar desde la interfaz, inicia el programa con run.py."
                )
            with store.connect() as con:
                con.execute("PRAGMA wal_checkpoint(FULL)")
            shutting_down = True
            background_tasks.add_task(jobs.close)
            background_tasks.add_task(callback)
            return {"closed": True}

    @app.post("/api/restart")
    def restart():
        nonlocal jobs, shutting_down
        with session_lock:
            if not shutting_down:
                raise HTTPException(409, "El programa ya est\u00e1 abierto.")
            # Wait for shutdown cleanup before replacing the scheduler.
            jobs.close()
            jobs = Jobs(store, settings)
            app.state.jobs = jobs
            shutting_down = False
            return {"restarted": True}

    @app.get("/api/projects/{project_id}/datasets")
    def datasets(project_id: str):
        project(project_id)
        return [public_dataset(d) for d in store.list("dataset", project_id)]

    @app.post("/api/projects/{project_id}/uploads", status_code=202)
    def upload(project_id: str, file: UploadFile = File(...), sheet: str | None = Form(None)):
        project(project_id)
        filename = Path((file.filename or "archivo").replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if suffix not in (".csv", ".parquet", ".json", ".jsonl", ".ndjson", ".xlsx"):
            raise ValueError("Formatos admitidos: CSV, Parquet, JSON, JSONL, NDJSON y XLSX.")
        directory = store.root / "projects" / project_id / "originals"
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / (uid() + suffix)
        size = 0
        try:
            with destination.open("wb") as out:
                while block := file.file.read(4 * 1024 * 1024):
                    size += len(block)
                    if size > settings.max_upload_gb * 1024**3:
                        raise HTTPException(413, "Archivo demasiado grande.")
                    out.write(block)
            if size == 0:
                raise ValueError("El archivo está vacío.")
            return jobs.submit(
                project_id,
                "import",
                input={
                    "name": filename,
                    "path": str(destination.relative_to(store.root)),
                    "format": suffix.lstrip("."),
                    "sheet": sheet,
                    "bytes": size,
                },
            )
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            file.file.close()

    @app.get("/api/projects/{project_id}/datasets/{dataset_id}/preview")
    def preview(
        project_id: str,
        dataset_id: str,
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0, le=10000000),
    ):
        data = store.dataset(project_id, dataset_id)
        with query_lock, query_engine(project_id) as engine:
            return {
                "rows": engine.preview(engine.view(data), limit, offset),
                "offset": offset,
                "limit": limit,
            }

    @app.post("/api/projects/{project_id}/runs", status_code=202)
    def run(project_id: str, body: RunRequest):
        project(project_id)
        store.dataset(project_id, body.dataset_id)
        if body.plan.questions:
            raise ValueError("Resuelve las preguntas de la IA antes de ejecutar el plan.")
        for step in body.plan.steps:
            if step.dataset_id:
                store.dataset(project_id, step.dataset_id)
        return jobs.submit(
            project_id, "pipeline", dataset_id=body.dataset_id, plan=body.plan.model_dump()
        )

    @app.get("/api/projects/{project_id}/jobs")
    def list_jobs(project_id: str):
        project(project_id)
        return store.list("job", project_id)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        return store.get("job", job_id)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return jobs.cancel(job_id)

    @app.get("/api/projects/{project_id}/audit")
    def audit(project_id: str):
        project(project_id)
        return store.list("audit", project_id)[:200]

    @app.post("/api/projects/{project_id}/sample-consents")
    def sample_consent(project_id: str, body: SampleConsent):
        project(project_id)
        samples = []
        with query_lock, query_engine(project_id) as engine:
            for dataset_id in body.dataset_ids:
                data = store.dataset(project_id, dataset_id)
                names = [c["name"] for c in data["profile"]["columns"]]
                if any(c not in names for c in body.columns):
                    raise ValueError("Alguna columna seleccionada no existe en el archivo.")
                rows = engine.preview(engine.view(data), body.rows)
                samples.append(
                    {
                        "dataset_id": dataset_id,
                        "rows": [{c: row[c] for c in body.columns} for row in rows],
                    }
                )
        if len(json.dumps(samples, ensure_ascii=False).encode()) > 32768:
            raise ValueError("Muestra demasiado grande; selecciona menos columnas o filas.")
        result = store.put(
            "consent",
            {
                "project_id": project_id,
                "samples": samples,
                "expires_at": expires_at(),
                "used": False,
            },
            project_id,
        )
        store.audit(
            project_id,
            "sample_previewed",
            {"consent_id": result["id"], "columns": body.columns, "rows": body.rows},
        )
        # Nothing is transmitted at this point. The user must explicitly use this token in interpret.
        return result

    @app.post("/api/projects/{project_id}/interpret")
    def interpret(project_id: str, body: InterpretRequest):
        project(project_id)
        active_data = store.dataset(project_id, body.dataset_id)
        if re.search(r"\b(riesgo|risk)\b", body.instruction, re.IGNORECASE) and not any(
            m.get("is_target") and m.get("target_meaning") for m in dictionary(active_data).values()
        ):
            plan = Plan(
                questions=[
                    "¿Qué variable define el riesgo, de dónde procede y qué significan sus códigos? Define el objetivo en el diccionario o explícitalo en la instrucción; solo se realizarán comparaciones descriptivas."
                ]
            )
            return store.put(
                "plan",
                {
                    "project_id": project_id,
                    "dataset_id": body.dataset_id,
                    "instruction": body.instruction,
                    "plan": plan.model_dump(),
                },
                project_id,
            )
        with ai_lock:
            if len(body.instruction) > settings.max_instruction_chars:
                raise ValueError("Instrucción demasiado larga.")
            all_data = store.list("dataset", project_id)
            if len(all_data) > 20:
                selected = store.dataset(project_id, body.dataset_id)
                all_data = [selected] + [d for d in all_data if d["id"] != body.dataset_id][:19]
            context = {
                "active_dataset_id": body.dataset_id,
                "datasets": [
                    {
                        "id": d["id"],
                        "columns": [
                            {"name": c["name"], "type": c["type"]} for c in d["profile"]["columns"]
                        ],
                    }
                    for d in all_data
                ],
            }
            if body.consent_id:
                consent = store.get("consent", body.consent_id)
                if consent["project_id"] != project_id or not consent_valid(consent):
                    raise ValueError(
                        "La autorización ha caducado o ya se utilizó. Previsualiza otra muestra."
                    )
                for sample in consent["samples"]:
                    store.dataset(project_id, sample["dataset_id"])
                context["authorized_samples"] = consent["samples"]
            if len(json.dumps(context, ensure_ascii=False).encode()) > 64000:
                raise ValueError(
                    "Contexto demasiado grande; reduce el número de tablas o columnas del proyecto."
                )
            # Consume before transmission: failure also requires a new explicit authorization.
            if body.consent_id:
                store.update("consent", body.consent_id, used=True)
            store.audit(
                project_id,
                "ai_request",
                {
                    "dataset_id": body.dataset_id,
                    "consent_id": body.consent_id,
                    "samples_sent": bool(body.consent_id),
                    "instruction_chars": len(body.instruction),
                },
            )
            try:
                plan = interpreter.interpret(body.instruction, context)
            except httpx_error_types() as exc:
                raise ValueError(
                    "No se pudo conectar con la API de IA. No se ha ejecutado ningún paso."
                ) from exc
            for step in plan.steps:
                if step.dataset_id:
                    store.dataset(project_id, step.dataset_id)
                if step.allow_many_to_many:
                    raise ValueError("La IA no puede autorizar uniones que multiplican filas.")
            record = store.put(
                "plan",
                {
                    "project_id": project_id,
                    "dataset_id": body.dataset_id,
                    "instruction": body.instruction,
                    "plan": plan.model_dump(),
                },
                project_id,
            )
            return record

    @app.post("/api/projects/{project_id}/datasets/{dataset_id}/chart")
    def chart(project_id: str, dataset_id: str, spec: ChartSpec):
        data = store.dataset(project_id, dataset_id)
        if data["profile"]["rows"] > 100_000:
            raise HTTPException(
                409, "Usa /analyses para cálculos cancelables sobre datasets grandes."
            )
        with query_lock, query_engine(project_id) as engine:
            return engine.chart(engine.view(data), spec, metadata=dictionary(data), dataset=data)

    @app.get("/api/projects/{project_id}/datasets/{dataset_id}/dictionary")
    def get_dictionary(project_id: str, dataset_id: str):
        data = store.dataset(project_id, dataset_id)
        return {
            "columns": dictionary(data),
            "revision": data.get("dictionary_revision", 0),
            "history": data.get("dictionary_history", []),
        }

    @app.post("/api/projects/{project_id}/datasets/{dataset_id}/dictionary")
    def edit_dictionary(project_id: str, dataset_id: str, body: DictionaryUpdate):
        for meta in body.columns.values():
            if (
                meta.minimum is not None
                and meta.maximum is not None
                and meta.minimum > meta.maximum
            ):
                raise ValueError("El mínimo de la restricción supera el máximo.")
            if meta.is_target and not meta.target_meaning.strip():
                raise ValueError("Define el significado y procedencia de la variable objetivo.")
        data = store.update_dictionary(
            project_id, dataset_id, {n: m.model_dump() for n, m in body.columns.items()}
        )
        store.audit(
            project_id,
            "dictionary_updated",
            {
                "dataset_id": dataset_id,
                "revision": data["dictionary_revision"],
                "columns": list(body.columns),
            },
        )
        return {"columns": dictionary(data), "revision": data["dictionary_revision"]}

    @app.post("/api/projects/{project_id}/datasets/{dataset_id}/analyses", status_code=202)
    def analyse(project_id: str, dataset_id: str, body: AnalysisRequest):
        data = store.dataset(project_id, dataset_id)
        required = {
            "chart": body.chart,
            "quality": body.quality,
            "export": body.export,
            "categories": body.category_column,
        }
        if required[body.kind] is None or any(
            v is not None for k, v in required.items() if k != body.kind
        ):
            raise ValueError("Indica solo los parámetros correspondientes al tipo de análisis.")
        parameters = body.model_dump()
        key = calculation_key(data, parameters)
        return jobs.submit(
            project_id,
            "analysis",
            dataset_id=dataset_id,
            analysis=parameters,
            dictionary_revision=data.get("dictionary_revision", 0),
            cache_key=key,
        )

    @app.get("/api/projects/{project_id}/datasets/{dataset_id}/categories")
    def categories(project_id: str, dataset_id: str, column: str):
        data = store.dataset(project_id, dataset_id)
        if column not in dictionary(data):
            raise ValueError("Columna desconocida.")
        col = next(c for c in data["profile"]["columns"] if c["name"] == column)
        return {
            "values": col.get("frequencies", []),
            "truncated": col.get("categories_truncated", False),
            "scope": "Perfil guardado: hasta 20 categorías; usa /analyses kind=categories para recalcular hasta 200.",
        }

    @app.post("/api/projects/{project_id}/datasets/{dataset_id}/exports")
    def export(project_id: str, dataset_id: str, body: ExportRequest):
        data = store.dataset(project_id, dataset_id)
        if data["profile"]["rows"] > 100_000:
            raise HTTPException(
                409, "Usa /analyses kind=export para exportar datasets grandes con cancelación."
            )
        export_id = uid()
        directory = store.root / "projects" / project_id / "exports"
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / (export_id + ".html")
        with query_lock, query_engine(project_id) as engine:
            summary = export_dashboard(
                engine,
                engine.view(data),
                body,
                output,
                {
                    "dataset_id": dataset_id,
                    "project_id": project_id,
                    "job_id": data["job_id"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "source_rows": data["profile"]["rows"],
                },
                dataset=data,
            )
        store.put(
            "export",
            {
                "id": export_id,
                "project_id": project_id,
                "path": str(output.relative_to(store.root)),
                "summary": summary,
            },
            project_id,
        )
        store.audit(project_id, "dashboard_exported", {"export_id": export_id, **summary})
        return {"download_url": f"/api/exports/{export_id}", **summary}

    @app.get("/api/projects/{project_id}/dashboards")
    def dashboards(project_id: str):
        project(project_id)
        return store.list("dashboard", project_id)

    @app.post("/api/projects/{project_id}/dashboards", status_code=201)
    def save_dashboard(project_id: str, body: DashboardCreate):
        data = store.dataset(project_id, body.dataset_id)
        with query_lock, query_engine(project_id) as engine:
            relation = engine.view(data)
            names = [c["name"] for c in engine.schema(relation)]
            for chart in body.charts:
                refs = (
                    [chart.x]
                    + ([chart.y] if chart.y else [])
                    + ([chart.group] if chart.group else [])
                    + chart.columns
                    + [f.column for f in chart.filters]
                )
                if not set(refs) <= set(names):
                    raise ValueError("El gráfico referencia columnas desconocidas.")
            if any(c not in names for c in body.filter_columns):
                raise ValueError("Alguna columna de filtro no existe.")
        result = store.put("dashboard", {"project_id": project_id, **body.model_dump()}, project_id)
        store.audit(project_id, "dashboard_saved", {"dashboard_id": result["id"]})
        return result

    @app.get("/api/exports/{export_id}")
    def download_export(export_id: str):
        record = store.get("export", export_id)
        return FileResponse(
            store.root / record["path"], media_type="text/html", filename="dashboard.html"
        )

    @app.get("/api/projects/{project_id}/datasets/{dataset_id}/download")
    def download_data(project_id: str, dataset_id: str):
        data = store.dataset(project_id, dataset_id)
        return FileResponse(
            store.root / data["path"],
            media_type="application/octet-stream",
            filename="datos-tratados.parquet",
        )

    @app.get("/api/projects/{project_id}/datasets/{dataset_id}/recipe")
    def recipe(project_id: str, dataset_id: str):
        data = store.dataset(project_id, dataset_id)
        return {
            "dataset_id": dataset_id,
            "parent_id": data.get("parent_id"),
            "plan": data.get("plan"),
            "history": data.get("history", []),
        }

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:

        @app.get("/")
        def build_required():
            return JSONResponse(
                {"message": "Construye el frontend: cd frontend; npm ci; npm run build"}
            )

    return app


def httpx_error_types():
    import httpx

    return httpx.HTTPError


app = create_app()
