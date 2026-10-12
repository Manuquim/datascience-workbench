"""One worker OS process per heavy job. Only the scheduler starts this module."""

import argparse
import shutil
import traceback
from dataclasses import replace
from pathlib import Path

from .config import Settings
from .engine import Engine, excel_to_csv, file_hash, literal, identifier, rows_json
from .models import AnalysisRequest, Plan
from .store import Store, uid, now
from .metadata import dictionary, suggest
from .exporter import export_dashboard


def run_job(root, job_id):
    settings = replace(Settings.from_env(), data_dir=Path(root))
    store = Store(settings.data_dir)
    job = store.get("job", job_id)
    settings = replace(settings, **job.get("resources", {}))
    project_id = job["project_id"]
    workspace = store.root / "projects" / project_id / "runs" / job_id
    workspace.mkdir(parents=True, exist_ok=True)

    def progress(number, message):
        store.update("job", job_id, progress=number, message=message)

    try:
        if not store.start_job(job_id):
            return
        with Engine(settings, store, project_id, workspace) as engine:
            if job["action"] == "analysis":
                data = store.dataset(project_id, job["dataset_id"])
                request = AnalysisRequest.model_validate(job["analysis"])
                if data.get("dictionary_revision", 0) != job.get("dictionary_revision", 0):
                    raise ValueError("El diccionario cambió; solicita un nuevo cálculo.")
                try:
                    cached = store.get("analysis_cache", job["cache_key"])["result"]
                except KeyError:
                    cached = None
                if cached is not None:
                    store.complete_analysis(
                        job_id,
                        {**cached, "cache_hit": True},
                        profile=cached if request.kind == "quality" else None,
                    )
                    return
                relation = engine.view(data)
                progress(0, "Calculando sobre el dataset completo con límites de recursos")
                updated_profile, export_record = None, None
                if request.kind == "chart":
                    result = engine.chart(
                        relation, request.chart, metadata=dictionary(data), dataset=data
                    )
                elif request.kind == "quality":
                    result = updated_profile = engine.profile(
                        relation, dictionary(data), request.quality
                    )
                elif request.kind == "categories":
                    if request.category_column not in dictionary(data):
                        raise ValueError("Columna desconocida.")
                    column = identifier(request.category_column)
                    values = rows_json(
                        engine.con.execute(
                            f"SELECT {column} AS value,count(*) AS count FROM {relation} GROUP BY {column} ORDER BY count DESC,CAST({column} AS VARCHAR) NULLS LAST LIMIT 201"
                        )
                    )
                    result = {
                        "values": values[:200],
                        "truncated": len(values) > 200,
                        "scope": "Frecuencias exactas sobre toda la tabla; hasta 200 categorías",
                    }
                else:
                    export_id = uid()
                    output = workspace / "dashboard.html"
                    summary = export_dashboard(
                        engine,
                        relation,
                        request.export,
                        output,
                        {
                            "dataset_id": data["id"],
                            "project_id": project_id,
                            "created_at": now(),
                            "source_rows": data["profile"]["rows"],
                        },
                        dataset=data,
                    )
                    export_record = {
                        "id": export_id,
                        "project_id": project_id,
                        "path": str(output.relative_to(store.root)),
                        "summary": summary,
                    }
                    result = {"download_url": f"/api/exports/{export_id}", **summary}
                published = store.complete_analysis(
                    job_id, result, job["cache_key"], updated_profile, export_record
                )
                if not published and request.kind == "export":
                    output.unlink(missing_ok=True)
                return
            elif job["action"] == "import":
                data = dict(job["input"])
                original = engine.path(data)
                checksum = file_hash(original)
                progress(0, "Leyendo archivo y normalizando a Parquet")
                sheet_name = None
                if data["format"] == "xlsx":
                    converted = workspace / "excel.csv"
                    sheet_name = excel_to_csv(original, converted, data.get("sheet"))
                    data.update(path=str(converted.relative_to(store.root)), format="csv")
                relation = engine.view(data)
                if len(engine.schema(relation)) > 200:
                    raise ValueError("Máximo 200 columnas por archivo en esta versión.")
                output = workspace / "result.parquet"
                engine.con.execute(
                    f"COPY (SELECT * FROM {relation}) TO {literal(str(output))} (FORMAT PARQUET, COMPRESSION ZSTD)"
                )
                data.update(path=str(output.relative_to(store.root)), format="parquet")
                relation = engine.view(data)
                progress(1, "Calculando calidad y estadísticas")
                profile = engine.profile(relation)
                dataset_payload = {
                    "project_id": project_id,
                    "name": job["input"]["name"],
                    "path": str(output.relative_to(store.root)),
                    "format": "parquet",
                    "original_path": job["input"]["path"],
                    "original_sha256": checksum,
                    "sheet": sheet_name,
                    "profile": profile,
                    "dictionary": {c["name"]: suggest(c) for c in profile["columns"]},
                    "dictionary_revision": 0,
                    "parent_id": None,
                    "job_id": job_id,
                }
            else:
                data = store.dataset(project_id, job["dataset_id"])
                plan = Plan.model_validate(job["plan"])
                output, profile, history, metadata = engine.execute_plan(data, plan, progress)
                dataset_payload = {
                    "project_id": project_id,
                    "name": plan.name,
                    "path": str(output.relative_to(store.root)),
                    "format": "parquet",
                    "profile": profile,
                    "parent_id": data["id"],
                    "job_id": job_id,
                    "plan": plan.model_dump(),
                    "history": history,
                    "dictionary": metadata,
                    "dictionary_revision": 0,
                    "source_dictionary_revision": data.get("dictionary_revision", 0),
                }
        # Intermediate materializations are no longer necessary after a successful run.
        for path in workspace.glob("step-*.parquet"):
            path.unlink()
        (workspace / "excel.csv").unlink(missing_ok=True)
        shutil.rmtree(workspace / "spill", ignore_errors=True)
        result = store.complete_job(job_id, dataset_payload)
        if result is None:
            output.unlink(missing_ok=True)
            return
        try:
            store.audit(project_id, "job_succeeded", {"job_id": job_id, "result_id": result["id"]})
        except Exception:
            # The published result stays valid even if an auxiliary audit write fails.
            (workspace / "audit-error.log").write_text(traceback.format_exc(), encoding="utf-8")
    except Exception as exc:
        # Diagnostics remain local. Never log API keys or external-provider response bodies.
        (workspace / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        message = str(exc)[:1500]
        store.fail_job(job_id, message)
        store.audit(project_id, "job_failed", {"job_id": job_id, "message": message})
        for path in workspace.glob("*.parquet"):
            path.unlink(missing_ok=True)
        (workspace / "dashboard.html").unlink(missing_ok=True)
        shutil.rmtree(workspace / "spill", ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    run_job(args.root, args.job)
