import json
import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.engine import Engine, literal
from app.exporter import export_dashboard
from app.main import create_app
from app.metadata import dictionary, numeric_type
from app.models import ChartSpec, ColumnMetadata, ExportRequest, Plan, QualityRequest
from app.statistics import calculation_key
from app.store import Store


@pytest.fixture
def engine(tmp_path):
    store = Store(tmp_path)
    with Engine(
        Settings(data_dir=tmp_path, memory_limit="128MB", threads=1), store, "p", tmp_path / "work"
    ) as engine:
        yield engine


def relation(engine, sql):
    engine.con.execute(f"CREATE OR REPLACE TEMP VIEW observations AS {sql}")
    return '"observations"'


def chart(engine, rel, **spec):
    return engine.chart(rel, ChartSpec(**spec))


def test_unequal_groups_counts_and_within_group_percentages(engine):
    rel = relation(
        engine,
        "SELECT CASE WHEN i<100 THEN 'A' ELSE 'B' END AS cohort, CASE WHEN i<60 OR i>=102 THEN 'yes' ELSE 'no' END AS answer FROM range(110) t(i)",
    )
    counts = chart(engine, rel, kind="bar", x="answer", group="cohort", aggregation="count")
    percents = chart(
        engine,
        rel,
        kind="bar",
        x="answer",
        group="cohort",
        aggregation="count",
        measure="percentage",
        denominator="group",
    )
    yes_counts = {r["series"]: r["value"] for r in counts["rows"] if r["x"] == "yes"}
    yes_percent = {r["series"]: r["value"] for r in percents["rows"] if r["x"] == "yes"}
    assert yes_counts == {"A": 60, "B": 8}
    assert yes_percent == {"A": 60, "B": 80}
    assert percents["provenance"]["denominators"] == [
        {"group": "A", "n": 100},
        {"group": "B", "n": 10},
    ]


@pytest.mark.parametrize(
    "missing,denominator,expected,used",
    [
        ("exclude", "used", 50, 2),
        ("exclude", "filtered", 100 / 3, 2),
        ("include", "used", 100 / 3, 3),
    ],
)
def test_missing_and_denominators(engine, missing, denominator, expected, used):
    rel = relation(engine, "SELECT * FROM (VALUES ('a'),('b'),(NULL)) t(category)")
    result = chart(
        engine,
        rel,
        x="category",
        aggregation="count",
        measure="percentage",
        missing=missing,
        denominator=denominator,
    )
    assert next(r["value"] for r in result["rows"] if r["x"] == "a") == pytest.approx(expected)
    assert result["provenance"]["used_rows"] == used
    assert result["provenance"]["filtered_rows"] == 3


def test_group_percent_rejects_missing_group_and_arbitrary_values(engine):
    rel = relation(engine, "SELECT 1 AS x,2 AS y")
    with pytest.raises(ValueError, match="grupo"):
        chart(engine, rel, x="x", denominator="group", measure="percentage")
    with pytest.raises(ValueError, match="frecuencias"):
        chart(engine, rel, x="x", y="y", aggregation="sum", measure="percentage")


def test_full_aggregation_beyond_previous_limits(engine):
    rel = relation(
        engine,
        "SELECT CASE WHEN i<20000 THEN 'head' ELSE 'tail' END AS category,i AS value FROM range(25050) t(i)",
    )
    result = chart(engine, rel, x="category", aggregation="count")
    assert {r["x"]: r["value"] for r in result["rows"]} == {"head": 20000, "tail": 5050}
    sums = chart(
        engine,
        rel,
        x="category",
        y="value",
        aggregation="sum",
        filters=[{"column": "category", "value": "tail"}],
    )
    assert sums["rows"][0]["value"] == sum(range(20000, 25050))
    assert sums["provenance"]["used_rows"] == 5050
    assert not sums["truncated"]


def test_common_histogram_edges_and_zero_bins(engine):
    rel = relation(
        engine, "SELECT * FROM (VALUES ('A',1.0),('A',2.0),('B',10.0),('B',11.0)) t(cohort,value)"
    )
    result = chart(engine, rel, kind="histogram", x="value", group="cohort", bins=2)
    assert [(r["series"], r["value"]) for r in result["rows"]] == [
        ("A", 2),
        ("A", 0),
        ("B", 0),
        ("B", 2),
    ]
    assert [(r["bin_start"], r["bin_end"]) for r in result["rows"]] == [(1, 6), (6, 11)] * 2


def test_histogram_range_denominator_and_constant(engine):
    rel = relation(engine, "SELECT * FROM (VALUES (1.0),(2.0),(10.0),(NULL)) t(value)")
    result = chart(
        engine,
        rel,
        kind="histogram",
        x="value",
        bins=2,
        bin_start=1,
        bin_end=2,
        measure="percentage",
        denominator="filtered",
    )
    assert sum(r["value"] for r in result["rows"]) == 50
    assert result["provenance"]["used_rows"] == 2
    rel = relation(engine, "SELECT 4.0 AS value FROM range(3)")
    result = chart(engine, rel, kind="histogram", x="value", bins=2)
    assert sum(r["n"] for r in result["rows"]) == 3


def test_box_quartiles_whiskers_and_outliers(engine):
    rel = relation(engine, "SELECT * FROM (VALUES (1.0),(2.0),(3.0),(4.0),(100.0)) t(value)")
    result = chart(engine, rel, kind="box", x="value")
    assert result["rows"] == [
        {
            "group": None,
            "n": 5,
            "q1": 2.0,
            "median": 3.0,
            "q3": 4.0,
            "lower_whisker": 1.0,
            "upper_whisker": 4.0,
            "outliers": 1,
        }
    ]
    assert (
        "type 7" in result["provenance"]["method"][0]
        or "tipo 7" in result["provenance"]["method"][0]
    )


def test_correlation_semantics_constant_nonfinite_and_pairs(engine):
    rel = relation(
        engine,
        "SELECT * FROM (VALUES (1.0,2.0,0,1,1.0),(2.0,4.0,1,2,1.0),(3.0,6.0,0,3,1.0),(4.0,NULL,1,4,1.0),('NaN'::DOUBLE,8.0,1,5,1.0)) t(x,y,code,id,constant)",
    )
    result = chart(
        engine, rel, kind="correlation", x="x", columns=["x", "y", "code", "id", "constant"]
    )
    assert result["figure"]["data"][0]["x"] == ["x", "y", "constant"]
    xy = next(r for r in result["rows"] if r["x"] == "x" and r["y"] == "y")
    assert xy["value"] == pytest.approx(1)
    assert xy["n"] == 3
    assert all(r["value"] is None for r in result["rows"] if "constant" in (r["x"], r["y"]))
    with pytest.raises(ValueError, match="numérica"):
        chart(engine, rel, kind="scatter", x="code", y="y")


def test_reproducible_scatter_sampling(engine):
    rel = relation(engine, "SELECT i AS x,i*2 AS y FROM range(20000) t(i)")
    first = chart(engine, rel, kind="scatter", x="x", y="y", sample_size=25, seed=7)
    second = chart(engine, rel, kind="scatter", x="x", y="y", sample_size=25, seed=7)
    other = chart(engine, rel, kind="scatter", x="x", y="y", sample_size=25, seed=8)
    assert first["rows"] == second["rows"]
    assert first["rows"] != other["rows"]
    assert len(first["rows"]) == 25
    assert first["provenance"]["sampled"] and first["provenance"]["used_rows"] == 20000
    assert max(r["x"] for r in first["rows"]) > 5000


def test_empty_data_and_nonfinite_values(engine):
    rel = relation(engine, "SELECT 1.0 AS x,2.0 AS y WHERE false")
    assert chart(engine, rel, kind="scatter", x="x", y="y")["rows"] == []
    assert sum(r["n"] for r in chart(engine, rel, kind="histogram", x="x")["rows"]) == 0
    assert engine.profile(rel)["rows"] == 0
    rel = relation(
        engine, "SELECT * FROM (VALUES (1.0),(NULL),('NaN'::DOUBLE),('Infinity'::DOUBLE)) t(x)"
    )
    col = engine.profile(rel)["columns"][0]
    assert (col["valid"], col["nulls"], col["nonfinite"], col["mean"]) == (1, 1, 2, 1)
    assert not numeric_type("INTERVAL") and numeric_type("DECIMAL(10,2)")


def test_exact_profile_rules_and_duplicate_keys(engine):
    rel = relation(
        engine, "SELECT * FROM (VALUES (1,1.0),(1,1.0),(2,2.0),(2,100.0),(NULL,NULL)) t(code,value)"
    )
    metadata = {
        "code": ColumnMetadata(
            semantic_type="nominal", expected_categories=[1], nullable=False
        ).model_dump(),
        "value": ColumnMetadata(semantic_type="continuous", maximum=10).model_dump(),
    }
    result = engine.profile(
        rel, metadata, QualityRequest(duplicate_keys=["code"], exact_quantiles=True)
    )
    assert result["exact_duplicates"] == 1
    assert result["key_duplicates"]["count"] == 2
    assert result["columns"][0]["rule_violations"] == 3
    assert "mean" not in result["columns"][0]
    assert result["columns"][1]["rule_violations"] == 1
    assert "exact" in result["columns"][1]["quantile_method"]


def test_category_limit_does_not_publish_partial_percentage(engine):
    rel = relation(engine, "SELECT i AS category FROM range(201) t(i)")
    with pytest.raises(ValueError, match="porcentaje parcial"):
        chart(
            engine, rel, x="category", aggregation="count", measure="percentage", category_limit=200
        )


def test_dictionary_lineage_and_units_in_pipeline(engine):
    source = engine.store.root / "source.parquet"
    engine.con.execute(
        f"COPY (SELECT 1 AS id,2.0 AS amount UNION ALL SELECT 2,4.0) TO {literal(str(source))} (FORMAT PARQUET)"
    )
    rel = relation(engine, f"SELECT * FROM read_parquet({literal(str(source))})")
    data = engine.store.put(
        "dataset",
        {
            "project_id": "p",
            "path": "source.parquet",
            "format": "parquet",
            "profile": engine.profile(rel),
        },
        "p",
    )
    engine.store.update_dictionary(
        "p",
        data["id"],
        {
            "amount": ColumnMetadata(
                semantic_type="continuous", unit="EUR", description="Sales"
            ).model_dump()
        },
    )
    data = engine.store.dataset("p", data["id"])
    _, _, history, meta = engine.execute_plan(
        data,
        Plan(
            steps=[
                {"op": "rename", "column": "amount", "alias": "sales"},
                {
                    "op": "aggregate",
                    "columns": [],
                    "metrics": [{"column": "sales", "function": "sum", "alias": "total"}],
                },
            ]
        ),
        lambda *_: None,
    )
    assert meta["total"]["unit"] == "EUR"
    assert meta["total"]["semantic_type"] == "continuous"
    assert "aggregate" in [r["operation"] for r in meta["total"]["lineage"]]
    assert history[1]["rows_before"] == 2 and history[1]["rows_delta"] == -1
    assert dictionary(data)["amount"]["unit"] == "EUR"


def test_export_same_aggregate_figure_and_fixed_filters(engine, tmp_path):
    rel = relation(
        engine,
        "SELECT CASE WHEN i<20000 THEN 'head' ELSE 'tail' END AS category FROM range(25050) t(i)",
    )
    spec = ChartSpec(x="category", aggregation="count", measure="percentage")
    expected = engine.chart(rel, spec)
    output = tmp_path / "chart.html"
    summary = export_dashboard(
        engine, rel, ExportRequest(charts=[spec], filter_columns=["category"], limit=1), output, {}
    )
    document = output.read_text(encoding="utf-8")
    expression = document.split("const data=JSON.parse(")[1].split(");\nconst selected=")[0]
    payload = json.loads(json.loads(expression))
    assert payload["results"][0]["figure"] == expected["figure"]
    assert payload["results"][0]["provenance"]["used_rows"] == 25050
    assert payload["rows"] == [] and payload["filters"] == []
    assert summary["disabled_filters"] == ["category"] and not summary["truncated"]
    assert "necesitan backend" in document and 'src="https://' not in document


def test_cache_identity_and_cancelled_publication(engine):
    store = engine.store
    data = store.put(
        "dataset", {"project_id": "p", "path": "unused", "dictionary_revision": 0}, "p"
    )
    base = calculation_key(data, {"filters": [], "seed": 42})
    assert base != calculation_key(data, {"filters": [{"column": "x", "value": 1}], "seed": 42})
    assert base != calculation_key({**data, "dictionary_revision": 1}, {"filters": [], "seed": 42})
    job = store.put("job", {"project_id": "p", "dataset_id": data["id"], "status": "running"}, "p")
    store.cancel_job(job["id"])
    assert not store.complete_analysis(job["id"], {"value": 1}, base)
    assert store.list("analysis_cache") == []


def wait(client, ident):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = client.get(f"/api/jobs/{ident}").json()
        if result["status"] not in ("running", "queued"):
            return result
        time.sleep(0.05)
    raise AssertionError("Timed out")


def test_analysis_jobs_cache_dictionary_and_private_ai_context(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, memory_limit="128MB", threads=1))
    with TestClient(app) as client:
        p = client.post("/api/projects", json={"name": "Stats"}).json()["id"]
        base = f"/api/projects/{p}"
        imported = client.post(
            base + "/uploads", files={"file": ("data.csv", b"category,value\na,1\na,2\nb,3\n")}
        ).json()
        data_id = wait(client, imported["id"])["result_id"]
        path = base + f"/datasets/{data_id}"
        request = {"kind": "chart", "chart": {"x": "category", "aggregation": "count"}}
        first = client.post(path + "/analyses", json=request)
        assert first.status_code == 202
        first_job = wait(client, first.json()["id"])
        assert first_job["status"] == "succeeded", first_job
        assert first_job["resources"]["memory_limit"] == "128MB"
        second = wait(client, client.post(path + "/analyses", json=request).json()["id"])
        assert second["result"]["cache_hit"] is True
        metadata = ColumnMetadata(semantic_type="nominal", labels={"a": "Alpha"}).model_dump()
        assert (
            client.post(path + "/dictionary", json={"columns": {"category": metadata}}).status_code
            == 200
        )
        third = wait(client, client.post(path + "/analyses", json=request).json()["id"])
        assert not third["result"].get("cache_hit")
        assert "Alpha" in third["result"]["figure"]["data"][0]["x"]
        clarification = client.post(
            base + "/interpret", json={"dataset_id": data_id, "instruction": "compara el riesgo"}
        )
        assert clarification.status_code == 200 and clarification.json()["plan"]["questions"]
        assert app.state.store.list("audit", p)[0]["action"] != "ai_request"


def test_low_memory_failure_never_publishes_results(tmp_path):
    with Engine(
        Settings(data_dir=tmp_path, memory_limit="4MB", threads=1),
        Store(tmp_path),
        "p",
        tmp_path / "work",
    ) as engine:
        rel = relation(
            engine, "SELECT i AS category,repeat('x',100) || i AS value FROM range(100000) t(i)"
        )
        with pytest.raises(Exception, match="memory|Memory"):
            chart(engine, rel, x="category", aggregation="count", category_limit=100)
        assert engine.store.list("analysis_cache") == []


def test_running_analysis_can_be_cancelled(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, memory_limit="128MB", threads=1))
    store = app.state.store
    project = store.put("project", {"name": "Cancellation"})["id"]
    with Engine(
        Settings(data_dir=tmp_path, memory_limit="128MB", threads=1),
        store,
        project,
        tmp_path / "generator",
    ) as engine:
        source = tmp_path / "large.parquet"
        projection = ",".join(f"(i%10000*{j + 1})::DOUBLE AS v{j}" for j in range(12))
        engine.con.execute(
            f"COPY (SELECT {projection} FROM range(2000000) t(i)) TO {literal(str(source))} (FORMAT PARQUET)"
        )
    columns = [{"name": f"v{j}", "type": "DOUBLE"} for j in range(12)]
    data = store.put(
        "dataset",
        {
            "project_id": project,
            "path": "large.parquet",
            "format": "parquet",
            "profile": {"rows": 2000000, "columns": columns},
        },
        project,
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project}/datasets/{data['id']}/analyses",
            json={
                "kind": "chart",
                "chart": {
                    "kind": "correlation",
                    "x": "v0",
                    "columns": [c["name"] for c in columns],
                },
            },
        )
        ident = response.json()["id"]
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            current = store.get("job", ident)
            if current["status"] == "running":
                break
            assert current["status"] == "queued", current
            time.sleep(0.01)
        assert store.get("job", ident)["status"] == "running"
        assert client.post(f"/api/jobs/{ident}/cancel", json={}).json()["status"] == "cancelled"
    assert store.get("job", ident)["status"] == "cancelled"
    assert "result" not in store.get("job", ident)
    assert store.list("analysis_cache") == []
