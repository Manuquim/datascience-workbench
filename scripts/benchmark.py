"""Reproducible larger-than-memory sorting probe; not a maximum-capacity guarantee."""

import json
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.engine import Engine, literal  # noqa: E402
from app.models import Plan  # noqa: E402
from app.store import Store  # noqa: E402


def main():
    import duckdb

    root = Path(tempfile.mkdtemp(prefix="dsw-benchmark-"))
    rows = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000
    started = time.monotonic()
    try:
        source = root / "source.parquet"
        with duckdb.connect(config={"threads": 2, "memory_limit": "128MB"}) as con:
            con.execute(
                "COPY (SELECT i AS id, hash(i) AS sort_value, "
                + ", ".join(f"i * {n} AS value_{n}" for n in range(1, 9))
                + f" FROM range({rows}) t(i)) "
                f"TO {literal(str(source))} (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        store = Store(root)
        data = store.put(
            "dataset",
            {"project_id": "benchmark", "path": "source.parquet", "format": "parquet"},
            "benchmark",
        )
        settings = replace(
            Settings.from_env(), data_dir=root, memory_limit="128MB", threads=1, temp_limit="2GB"
        )
        stats_path = root / "query-profile.json"
        with Engine(settings, store, "benchmark", root / "run") as engine:
            relation = engine.view(data)
            engine.con.execute("PRAGMA enable_profiling='json'")
            engine.con.execute(f"PRAGMA profiling_output={literal(str(stats_path))}")
            sql, _ = engine.compile_step(
                relation, Plan(steps=[{"op": "sort", "columns": ["sort_value"]}]).steps[0]
            )
            engine.con.execute(
                f"COPY ({sql}) TO {literal(str(root / 'sorted.parquet'))} (FORMAT PARQUET, ROW_GROUP_SIZE 16384)"
            )
            stats = json.loads(stats_path.read_text())
            engine.con.execute("PRAGMA disable_profiling")
            output_rows = engine.con.execute(
                f"SELECT COUNT(*) FROM read_parquet({literal(str(root / 'sorted.parquet'))})"
            ).fetchone()[0]
        result = {
            "rows": rows,
            "result_rows": output_rows,
            "duckdb_memory_limit": "128MB",
            "logical_payload_bytes_minimum": rows * 10 * 8,
            "input_parquet_bytes": source.stat().st_size,
            "peak_temp_disk_bytes": stats.get("system_peak_temp_dir_size"),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "scope": "Synthetic Parquet sort; not a multi-GB capacity guarantee.",
        }
        assert output_rows == rows
        print(json.dumps(result, indent=2))
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
