import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class Store:
    """SQLite stores metadata; row data lives in immutable files."""

    def __init__(self, root, recover=False):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = root / "metadata.sqlite3"
        with self.connect() as con:
            con.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS records (
                    kind TEXT NOT NULL, id TEXT PRIMARY KEY, project_id TEXT,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS records_project ON records(kind, project_id);
            """)
            interrupted = con.execute("SELECT id,payload FROM records WHERE kind='job'").fetchall()
            for row in interrupted if recover else []:
                p = json.loads(row["payload"])
                if p["status"] in ("running", "queued"):
                    p.update(
                        status="interrupted", message="Ejecución interrumpida; vuelve a lanzarla."
                    )
                    con.execute(
                        "UPDATE records SET payload=? WHERE id=?", (json.dumps(p), row["id"])
                    )

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def put(self, kind, payload, project_id=None):
        payload = {"id": uid(), "created_at": now(), **payload}
        with self.connect() as con:
            con.execute(
                "INSERT INTO records VALUES (?,?,?,?,?)",
                (
                    kind,
                    payload["id"],
                    project_id,
                    json.dumps(payload, ensure_ascii=False),
                    payload["created_at"],
                ),
            )
        return payload

    def get(self, kind, ident):
        with self.connect() as con:
            row = con.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, ident)
            ).fetchone()
        if not row:
            raise KeyError("No existe el recurso solicitado.")
        return json.loads(row[0])

    def list(self, kind, project_id=None):
        with self.connect() as con:
            rows = con.execute(
                "SELECT payload FROM records WHERE kind=? "
                "AND (? IS NULL OR project_id=?) ORDER BY created_at DESC",
                (kind, project_id, project_id),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def update(self, kind, ident, **changes):
        with self.connect() as con:
            row = con.execute(
                "SELECT payload FROM records WHERE kind=? AND id=?", (kind, ident)
            ).fetchone()
            if not row:
                raise KeyError(ident)
            payload = {**json.loads(row[0]), **changes}
            con.execute(
                "UPDATE records SET payload=? WHERE kind=? AND id=?",
                (json.dumps(payload), kind, ident),
            )
        return payload

    def dataset(self, project_id, ident):
        data = self.get("dataset", ident)
        if data["project_id"] != project_id:
            raise KeyError("El archivo no pertenece al proyecto.")
        return data

    def update_dictionary(self, project_id, ident, changes):
        from .metadata import dictionary

        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT payload FROM records WHERE kind='dataset' AND id=?", (ident,)
            ).fetchone()
            if not row:
                raise KeyError("No existe el dataset.")
            data = json.loads(row[0])
            if data["project_id"] != project_id:
                raise KeyError("El dataset no pertenece al proyecto.")
            current = dictionary(data)
            if not set(changes) <= set(current):
                raise ValueError("Columna de diccionario desconocida.")
            history = data.get("dictionary_history", [])
            for name, change in changes.items():
                history.append(
                    {"column": name, "before": current[name], "after": change, "at": now()}
                )
                current[name] = {
                    **change,
                    "suggested": False,
                    "lineage": current[name].get("lineage", []),
                }
            data.update(
                dictionary=current,
                dictionary_revision=data.get("dictionary_revision", 0) + 1,
                dictionary_history=history,
                profile_stale=True,
            )
            con.execute(
                "UPDATE records SET payload=? WHERE id=?",
                (json.dumps(data, ensure_ascii=False), ident),
            )
        return data

    def complete_analysis(self, job_id, result, cache_key=None, profile=None, export=None):
        """Atomic result publication; cancelled or outdated calculations never enter cache."""
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            job = json.loads(
                con.execute(
                    "SELECT payload FROM records WHERE kind='job' AND id=?", (job_id,)
                ).fetchone()[0]
            )
            if job["status"] not in ("queued", "running"):
                return False
            data = json.loads(
                con.execute(
                    "SELECT payload FROM records WHERE kind='dataset' AND id=?",
                    (job["dataset_id"],),
                ).fetchone()[0]
            )
            if data.get("dictionary_revision", 0) != job.get("dictionary_revision", 0):
                raise ValueError("El diccionario cambió durante el cálculo. Vuelve a solicitarlo.")
            if profile is not None:
                data["profile"] = profile
                data["profile_stale"] = False
                data["profile_dictionary_revision"] = data.get("dictionary_revision", 0)
                con.execute(
                    "UPDATE records SET payload=? WHERE id=?",
                    (json.dumps(data, ensure_ascii=False), data["id"]),
                )
            job.update(
                status="succeeded", result=result, finished_at=now(), message="Cálculo completado"
            )
            con.execute(
                "UPDATE records SET payload=? WHERE id=?",
                (json.dumps(job, ensure_ascii=False), job_id),
            )
            for kind, record in (
                ("analysis_cache", {"id": cache_key, "result": result} if cache_key else None),
                ("export", export),
            ):
                if record:
                    payload = {"created_at": now(), **record}
                    con.execute(
                        "INSERT OR REPLACE INTO records VALUES (?,?,?,?,?)",
                        (
                            kind,
                            payload["id"],
                            job["project_id"],
                            json.dumps(payload, ensure_ascii=False),
                            payload["created_at"],
                        ),
                    )
        return True

    def audit(self, project_id, action, details):
        return self.put("audit", {"action": action, "details": details}, project_id)

    def complete_job(self, job_id, dataset_payload):
        """Publish the dataset and successful job in one transaction, unless cancelled."""
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT payload FROM records WHERE id=? AND kind='job'", (job_id,)
            ).fetchone()
            job = json.loads(row[0])
            if job["status"] not in ("queued", "running"):
                return None
            data = {"id": uid(), "created_at": now(), **dataset_payload}
            con.execute(
                "INSERT INTO records VALUES (?,?,?,?,?)",
                (
                    "dataset",
                    data["id"],
                    job["project_id"],
                    json.dumps(data, ensure_ascii=False),
                    data["created_at"],
                ),
            )
            job.update(
                status="succeeded", result_id=data["id"], finished_at=now(), message="Completado"
            )
            con.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return data

    def cancel_job(self, job_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT payload FROM records WHERE id=? AND kind='job'", (job_id,)
            ).fetchone()
            if not row:
                raise KeyError("No existe la ejecución.")
            job = json.loads(row[0])
            changed = job["status"] in ("queued", "running")
            if changed:
                job.update(
                    status="cancelled", message="Cancelado por el usuario", finished_at=now()
                )
                con.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return job, changed

    def start_job(self, job_id):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT payload FROM records WHERE id=? AND kind='job'", (job_id,)
            ).fetchone()
            job = json.loads(row[0])
            if job["status"] != "queued":
                return False
            job.update(status="running", started_at=now(), message="Preparando ejecución")
            con.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return True

    def fail_job(self, job_id, message):
        with self.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute(
                "SELECT payload FROM records WHERE id=? AND kind='job'", (job_id,)
            ).fetchone()
            job = json.loads(row[0])
            if job["status"] not in ("queued", "running"):
                return False
            job.update(status="failed", finished_at=now(), message=message)
            con.execute("UPDATE records SET payload=? WHERE id=?", (json.dumps(job), job_id))
        return True
