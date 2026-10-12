"""Reproducible full-data exploration probe, with explicit resource and scope reporting."""

import argparse
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import duckdb  # noqa: E402
from app.config import Settings  # noqa: E402
from app.engine import Engine, literal  # noqa: E402
from app.models import ChartSpec  # noqa: E402
from app.store import Store  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--memory", default="128MB")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.rows < 100:
        parser.error("--rows must be >= 100")
    with tempfile.TemporaryDirectory(prefix="dsw-exploration-") as temp:
        root = Path(temp)
        source = root / "synthetic.parquet"
        with duckdb.connect(config={"memory_limit": args.memory, "threads": 1}) as con:
            con.execute(
                f"COPY (SELECT i AS id,i%5 AS code,CASE WHEN i%10<8 THEN 'A' ELSE 'B' END AS cohort,i%2 AS answer,(i%1000)::DOUBLE AS value,(i%1000)*2.0 AS paired FROM range({args.rows}) t(i)) TO {literal(str(source))} (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        store = Store(root)
        with Engine(
            Settings(data_dir=root, memory_limit=args.memory, threads=1, temp_limit="2GB"),
            store,
            "benchmark",
            root / "work",
        ) as engine:
            rel = engine.view({"path": "synthetic.parquet", "format": "parquet"})
            timing = {}
            results = {}
            specs = {
                "group_percentage": ChartSpec(
                    x="answer",
                    group="cohort",
                    aggregation="count",
                    measure="percentage",
                    denominator="group",
                ),
                "histogram": ChartSpec(kind="histogram", x="value", group="cohort", bins=20),
                "scatter": ChartSpec(
                    kind="scatter", x="value", y="paired", sample_size=1000, seed=42
                ),
                "correlation": ChartSpec(
                    kind="correlation", x="value", columns=["value", "paired", "code", "id"]
                ),
            }
            for name, spec in specs.items():
                started = time.perf_counter()
                result = engine.chart(rel, spec)
                timing[name] = round(time.perf_counter() - started, 3)
                results[name] = {
                    "used_rows": result["provenance"]["used_rows"],
                    "displayed_results": len(result["rows"]),
                    "sampled": result["provenance"]["sampled"],
                }
                assert result["provenance"]["used_rows"] == args.rows
            assert sum(r["n"] for r in engine.chart(rel, specs["histogram"])["rows"]) == args.rows
            started = time.perf_counter()
            profile = engine.profile(rel)
            timing["profile"] = round(time.perf_counter() - started, 3)
            assert profile["rows"] == args.rows
        report = {
            "environment": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "duckdb": duckdb.__version__,
                "machine": platform.machine(),
            },
            "rows": args.rows,
            "columns": 6,
            "parquet_bytes": source.stat().st_size,
            "duckdb_memory_limit": args.memory,
            "threads": 1,
            "temp_limit": "2GB",
            "seconds": timing,
            "results": results,
            "scope": "Synthetic compressed Parquet, full-data calculations. Does not measure total process RSS or certify arbitrary multi-GB files. DuckDB memory_limit is not a hard process memory limit.",
        }
        print(json.dumps(report, indent=2))
        if args.output:
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
