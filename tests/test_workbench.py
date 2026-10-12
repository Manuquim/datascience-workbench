import json
import time
from pathlib import Path

import duckdb
import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import OpenAIInterpreter, strict_schema
from app.config import Settings
from app.engine import identifier, literal
from app.main import create_app
from app.models import Plan, Step
from app.store import Store


class FakeInterpreter:
    def __init__(self):
        self.calls = []

    def interpret(self, instruction, context):
        self.calls.append((instruction, context))
        return Plan(name="Plan simulado", steps=[Step(op="deduplicate")])


def wait_job(client, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(0.05)
    raise AssertionError("La ejecución no terminó a tiempo.")


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    directory = tmp_path_factory.mktemp("workbench")
    interpreter = FakeInterpreter()
    app = create_app(
        Settings(data_dir=directory, api_key="test-key", ai_model="test-model"), interpreter
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Prueba"}).json()
        base = f"/api/projects/{project['id']}"
        source = b"fecha,producto_id,region,ingreso,coste\n2026-01-01,P1,Norte,100,50\n2026-01-01,P1,Norte,100,50\n2026-02-01,P2,Sur,200,100\n2026-02-02,P1,,0,0\n"
        response = client.post(base + "/uploads", files={"file": ("ventas.csv", source)})
        assert response.status_code == 202, response.text
        job = wait_job(client, response.json()["id"])
        assert job["status"] == "succeeded", job
        yield client, app, base, job["result_id"], interpreter


def result_for(client, base, dataset_id, plan):
    response = client.post(base + "/runs", json={"dataset_id": dataset_id, "plan": plan})
    assert response.status_code == 202, response.text
    return wait_job(client, response.json()["id"])


def test_import_profile_and_pagination(workspace):
    client, _, base, dataset_id, _ = workspace
    data = next(d for d in client.get(base + "/datasets").json() if d["id"] == dataset_id)
    assert data["profile"]["rows"] == 4
    assert next(c for c in data["profile"]["columns"] if c["name"] == "region")["nulls"] == 1
    response = client.get(base + f"/datasets/{dataset_id}/preview?limit=2&offset=1")
    assert len(response.json()["rows"]) == 2
    assert "path" not in data


def test_pipeline_reproducible_and_original_preserved(workspace):
    client, app, base, dataset_id, _ = workspace
    plan = {
        "name": "Total",
        "steps": [
            {"op": "deduplicate"},
            {
                "op": "aggregate",
                "columns": ["region"],
                "metrics": [{"function": "sum", "column": "ingreso", "alias": "total"}],
            },
            {"op": "sort", "columns": ["total"], "descending": True},
        ],
        "charts": [{"kind": "bar", "x": "region", "y": "total"}],
    }
    first = result_for(client, base, dataset_id, plan)
    second = result_for(client, base, dataset_id, plan)
    assert first["status"] == second["status"] == "succeeded", first
    a = client.get(base + f"/datasets/{first['result_id']}/preview").json()["rows"]
    b = client.get(base + f"/datasets/{second['result_id']}/preview").json()["rows"]
    assert a == b
    assert a[0]["total"] == 200
    original = app.state.store.get("dataset", dataset_id)
    assert (app.state.store.root / original["original_path"]).is_file()
    recipe = client.get(base + f"/datasets/{first['result_id']}/recipe").json()
    assert recipe["history"][0]["rows"] == 3
    assert recipe["parent_id"] == dataset_id


@pytest.mark.parametrize(
    "step",
    [
        {"op": "filter", "column": "ingreso", "operator": "gt", "value": 50},
        {"op": "select", "columns": ["region", "ingreso"]},
        {"op": "drop_nulls", "columns": ["region"]},
        {"op": "fill_null", "column": "region", "value": "Sin región"},
        {"op": "cast", "column": "ingreso", "target_type": "DOUBLE"},
        {"op": "rename", "column": "ingreso", "alias": "ventas"},
        {"op": "date_part", "column": "fecha", "part": "month", "alias": "mes"},
        {"op": "ratio", "column": "coste", "denominator": "ingreso", "alias": "ratio"},
    ],
)
def test_transformations(workspace, step):
    client, _, base, dataset_id, _ = workspace
    job = result_for(client, base, dataset_id, {"steps": [step]})
    assert job["status"] == "succeeded", job
    if step["op"] == "ratio":
        rows = client.get(base + f"/datasets/{job['result_id']}/preview").json()["rows"]
        assert rows[-1]["ratio"] is None


def test_invalid_cast_fails_without_publishing_dataset(workspace):
    client, _, base, dataset_id, _ = workspace
    before = len(client.get(base + "/datasets").json())
    job = result_for(
        client,
        base,
        dataset_id,
        {"steps": [{"op": "cast", "column": "region", "target_type": "BIGINT"}]},
    )
    assert job["status"] == "failed"
    assert len(client.get(base + "/datasets").json()) == before


def test_join_rejects_duplicate_right_keys(workspace):
    client, _, base, dataset_id, _ = workspace
    response = client.post(
        base + "/uploads",
        files={"file": ("products.csv", b"producto_id,categoria\nP1,A\nP1,B\nP2,C\n")},
    )
    other = wait_job(client, response.json()["id"])["result_id"]
    step = {
        "op": "join",
        "dataset_id": other,
        "left_key": "producto_id",
        "right_key": "producto_id",
    }
    failed = result_for(client, base, dataset_id, {"steps": [step]})
    assert failed["status"] == "failed"
    assert "multiplicar" in failed["message"]
    allowed = result_for(
        client, base, dataset_id, {"steps": [{**step, "allow_many_to_many": True}]}
    )
    assert allowed["status"] == "succeeded", allowed
    recipe = client.get(base + f"/datasets/{allowed['result_id']}/recipe").json()
    assert recipe["history"][0]["rows"] == 7
    assert recipe["history"][0]["warning"]


def test_concat(workspace):
    client, _, base, dataset_id, _ = workspace
    job = result_for(
        client, base, dataset_id, {"steps": [{"op": "concat", "dataset_id": dataset_id}]}
    )
    assert job["status"] == "succeeded", job
    data = next(d for d in client.get(base + "/datasets").json() if d["id"] == job["result_id"])
    assert data["profile"]["rows"] == 8


def test_ai_does_not_send_rows_by_default(workspace):
    client, _, base, dataset_id, interpreter = workspace
    response = client.post(
        base + "/interpret", json={"dataset_id": dataset_id, "instruction": "Elimina duplicados"}
    )
    assert response.status_code == 200, response.text
    context = interpreter.calls[-1][1]
    assert "authorized_samples" not in context
    assert all(set(c) == {"name", "type"} for d in context["datasets"] for c in d["columns"])
    assert all("preview" not in d and "name" not in d for d in context["datasets"])


def test_explicit_sample_consent_one_use_and_columns(workspace):
    client, _, base, dataset_id, interpreter = workspace
    preview = client.post(
        base + "/sample-consents",
        json={"dataset_ids": [dataset_id], "columns": ["region"], "rows": 2},
    )
    assert preview.status_code == 200, preview.text
    consent = preview.json()
    assert all(list(row) == ["region"] for row in consent["samples"][0]["rows"])
    request = {
        "dataset_id": dataset_id,
        "instruction": "Elimina duplicados",
        "consent_id": consent["id"],
    }
    assert client.post(base + "/interpret", json=request).status_code == 200
    assert interpreter.calls[-1][1]["authorized_samples"] == consent["samples"]
    assert client.post(base + "/interpret", json=request).status_code == 400


def test_expired_consent_is_rejected(workspace):
    client, app, base, dataset_id, _ = workspace
    consent = client.post(
        base + "/sample-consents", json={"dataset_ids": [dataset_id], "columns": ["region"]}
    ).json()
    app.state.store.update("consent", consent["id"], expires_at="2000-01-01T00:00:00+00:00")
    response = client.post(
        base + "/interpret",
        json={
            "dataset_id": dataset_id,
            "instruction": "Analiza datos",
            "consent_id": consent["id"],
        },
    )
    assert response.status_code == 400


def test_project_isolation(workspace):
    client, _, _, dataset_id, _ = workspace
    other = client.post("/api/projects", json={"name": "Otro"}).json()["id"]
    assert client.get(f"/api/projects/{other}/datasets/{dataset_id}/preview").status_code == 404


def test_schema_sql_injection_and_unknown_operation(workspace):
    client, _, base, dataset_id, _ = workspace
    assert (
        client.post(
            base + "/runs",
            json={
                "dataset_id": dataset_id,
                "plan": {"steps": [{"op": "sql", "query": "DROP TABLE"}]},
            },
        ).status_code
        == 422
    )
    job = result_for(
        client,
        base,
        dataset_id,
        {
            "steps": [
                {
                    "op": "filter",
                    "column": "ingreso",
                    "operator": "eq",
                    "value": "0); DROP TABLE test; --",
                }
            ]
        },
    )
    assert job["status"] == "failed"
    assert client.get(base + f"/datasets/{dataset_id}/preview").status_code == 200
    assert identifier('a"b') == '"a""b"'
    assert literal("a'b") == "'a''b'"


def test_questions_block_execution_and_cross_site_block(workspace):
    client, _, base, dataset_id, _ = workspace
    assert (
        client.post(
            base + "/runs", json={"dataset_id": dataset_id, "plan": {"questions": ["¿Qué fecha?"]}}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/projects", json={"name": "Malicioso"}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/projects", headers={"Host": "evil.example"}).status_code == 400

    headers = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate"}
    assert client.get("/", headers=headers).status_code == 200
    assert client.get("/api/projects", headers=headers).status_code == 403


def test_export_offline_filters_scope_and_safe_json(workspace):
    client, _, base, dataset_id, _ = workspace
    body = {
        "title": "</script><script>alert(1)</script>",
        "charts": [{"kind": "bar", "x": "region", "y": "ingreso"}],
        "filter_columns": ["region"],
        "limit": 2,
    }
    result = client.post(base + f"/datasets/{dataset_id}/exports", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["truncated"] is True
    html = client.get(result.json()["download_url"]).text
    assert "plotly.js" in html
    assert 'src="https://' not in html
    assert "Vista parcial" in html and "JSON.stringify(r[k])" in html
    assert "<title></script>" not in html
    assert "coste" not in html.split("const data=")[1].split("const selected=")[0]


def test_saved_dashboard(workspace):
    client, _, base, dataset_id, _ = workspace
    response = client.post(
        base + "/dashboards",
        json={
            "dataset_id": dataset_id,
            "title": "Ventas",
            "charts": [{"kind": "bar", "x": "region", "y": "ingreso"}],
            "filter_columns": ["region"],
        },
    )
    assert response.status_code == 201
    assert any(d["id"] == response.json()["id"] for d in client.get(base + "/dashboards").json())


@pytest.mark.parametrize(
    "extension,content",
    [
        ("json", b'[{"id":1,"value":10},{"id":2,"value":null}]'),
        ("jsonl", b'{"id":1,"value":10}\n{"id":2,"value":null}\n'),
    ],
)
def test_json_import(workspace, extension, content):
    client, _, base, _, _ = workspace
    response = client.post(base + "/uploads", files={"file": ("datos." + extension, content)})
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "succeeded", job
    assert len(client.get(base + f"/datasets/{job['result_id']}/preview").json()["rows"]) == 2


def test_excel_and_parquet_import(workspace, tmp_path):
    import io
    from openpyxl import Workbook

    client, _, base, _, _ = workspace
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["id", "nombre"])
    sheet.append([1, "Ana"])
    output = io.BytesIO()
    workbook.save(output)
    response = client.post(base + "/uploads", files={"file": ("datos.xlsx", output.getvalue())})
    assert wait_job(client, response.json()["id"])["status"] == "succeeded"
    parquet = tmp_path / "data.parquet"
    with duckdb.connect() as con:
        con.execute("COPY (SELECT 1 AS id, 'Hola' AS texto) TO ? (FORMAT PARQUET)", [str(parquet)])
    response = client.post(
        base + "/uploads", files={"file": ("datos.parquet", parquet.read_bytes())}
    )
    job = wait_job(client, response.json()["id"])
    assert job["status"] == "succeeded", job


def test_atomic_cancellation_prevents_publication(tmp_path):
    store = Store(tmp_path)
    job = store.put("job", {"status": "running", "project_id": "p"}, "p")
    current, changed = store.cancel_job(job["id"])
    assert changed and current["status"] == "cancelled"
    assert store.complete_job(job["id"], {"name": "No publicar"}) is None
    assert store.list("dataset") == []


def test_recovery_marks_running_jobs_interrupted(tmp_path):
    store = Store(tmp_path)
    job = store.put("job", {"status": "running"})
    assert Store(tmp_path, recover=True).get("job", job["id"])["status"] == "interrupted"


def test_openai_adapter_contract(tmp_path):
    captured = []
    plan = Plan(steps=[Step(op="deduplicate")]).model_dump()

    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(plan)}],
                    }
                ],
            },
        )

    adapter = OpenAIInterpreter(
        Settings(data_dir=tmp_path, api_key="secret", ai_model="chosen-model"),
        client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(handler), **kw),
    )
    assert adapter.interpret("Elimina duplicados", {"datasets": []}).steps[0].op == "deduplicate"
    assert captured[0]["store"] is False
    assert captured[0]["model"] == "chosen-model"
    schema = strict_schema(Plan.model_json_schema())
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["$defs"]["Step"]["additionalProperties"] is False


def test_invalid_chart_does_not_publish_pipeline(workspace):
    client, _, base, dataset_id, _ = workspace
    job = result_for(
        client,
        base,
        dataset_id,
        {"steps": [], "charts": [{"kind": "bar", "x": "missing", "y": "ingreso"}]},
    )
    assert job["status"] == "failed"


def test_example_recipe_totals_match_documentation(workspace):
    client, _, base, _, _ = workspace
    root = Path(__file__).resolve().parents[1]
    response = client.post(
        base + "/uploads",
        files={"file": ("ejemplo.csv", (root / "examples/ventas.csv").read_bytes())},
    )
    imported = wait_job(client, response.json()["id"])
    plan = json.loads((root / "examples/pipeline-ventas.json").read_text())
    result = result_for(client, base, imported["result_id"], plan)
    assert result["status"] == "succeeded", result
    rows = client.get(base + f"/datasets/{result['result_id']}/preview").json()["rows"]
    totals = {r["region"]: (r["ingreso_total"], r["coste_total"]) for r in rows}
    assert totals == {"Norte": (515, 315), "Sur": (550, 330), None: (80, 50)}


def test_cancelled_job_cannot_restart_or_fail(tmp_path):
    store = Store(tmp_path)
    job = store.put("job", {"status": "queued", "project_id": "p"}, "p")
    store.cancel_job(job["id"])
    assert store.start_job(job["id"]) is False
    assert store.fail_job(job["id"], "Late error") is False
    assert store.get("job", job["id"])["status"] == "cancelled"


def test_upload_limits_and_unsupported_format(workspace):
    client, _, base, _, _ = workspace
    assert client.post(base + "/uploads", files={"file": ("danger.exe", b"123")}).status_code == 400
    assert client.post(base + "/uploads", files={"file": ("empty.csv", b"")}).status_code == 400
    response = client.post(
        "/api/projects",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_home_summaries_use_metadata_and_keep_projects_separate(tmp_path):
    app = create_app(Settings(data_dir=tmp_path))
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Home"}).json()["id"]
        other = client.post("/api/projects", json={"name": "Other"}).json()["id"]
        store = app.state.store
        original = store.put("dataset", {"parent_id": None, "path": "missing-file.parquet"}, project)
        store.put("dataset", {"parent_id": original["id"], "path": "another-missing-file.parquet"}, project)
        store.put("dashboard", {"title": "Dashboard"}, project)
        store.put("dataset", {"parent_id": None}, other)
        summary = client.get("/api/project-summaries").json()
        assert summary[project]["datasets"] == 2
        assert summary[project]["derived"] == 1
        assert summary[project]["dashboards"] == 1
        assert summary[other]["datasets"] == 1
        assert summary[other]["dashboards"] == 0


def test_project_close_restore_and_shutdown(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    stopped = []
    app.state.shutdown_callback = lambda: stopped.append(True)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "Saved project"}).json()
        base = f"/api/projects/{project['id']}"
        assert client.post(base + "/open", json={}).json() == {}
        assert client.post("/api/shutdown", json={}).status_code == 409
        state = {"planText": "unfinished JSON", "instruction": "analyse", "chartSpecs": []}
        job = app.state.store.put("job", {"status": "running"}, project['id'])
        assert client.post(base + "/close", json=state).status_code == 409
        app.state.store.update("job", job['id'], status="succeeded")
        assert client.post(base + "/close", json=state).json() == {"saved": True}
        assert client.post("/api/shutdown", json={}).status_code == 200
        assert stopped == [True]
        assert client.post(base + "/open", json={}).status_code == 409
        assert client.get("/api/health").json()["status"] == "closed"
        assert app.state.jobs.closed
        assert client.post("/api/restart", json={}).json() == {"restarted": True}
        assert not app.state.jobs.closed
        assert client.post(base + "/open", json={}).json() == state
        assert client.post("/api/restart", json={}).status_code == 409
    restarted = create_app(settings)
    with TestClient(restarted) as client:
        assert client.post(base + "/open", json={}).json() == state
        assert client.get("/api/projects").json()[0]['id'] == project['id']
