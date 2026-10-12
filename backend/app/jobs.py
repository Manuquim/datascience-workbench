import os
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


class Jobs:
    def __init__(self, store, settings=None):
        self.store = store
        self.settings = settings
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dsw-scheduler")
        self.lock = threading.Lock()
        self.processes = {}
        self.futures = {}
        self.closed = False

    def submit(self, project_id, action, **payload):
        if self.closed:
            raise ValueError("El servidor se está cerrando.")
        if self.settings:
            payload["resources"] = {
                key: getattr(self.settings, key)
                for key in ("memory_limit", "threads", "temp_limit")
            }
        job = self.store.put(
            "job",
            {
                "project_id": project_id,
                "action": action,
                "status": "queued",
                "progress": 0,
                "message": "En cola",
                **payload,
            },
            project_id,
        )
        self.store.audit(project_id, "job_queued", {"job_id": job["id"], "action": action})
        with self.lock:
            self.futures[job["id"]] = self.pool.submit(self._execute, job["id"])
        return job

    def _execute(self, job_id):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        with self.lock:
            if self.store.get("job", job_id)["status"] == "cancelled" or self.closed:
                return
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "app.worker",
                    "--root",
                    str(self.store.root),
                    "--job",
                    job_id,
                ],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.processes[job_id] = process
        try:
            process.wait(timeout=int(os.getenv("DSW_JOB_TIMEOUT", "1800")))
            current = self.store.get("job", job_id)
            if current["status"] in ("queued", "running"):
                self.store.fail_job(job_id, "El proceso terminó inesperadamente.")
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            self.store.fail_job(job_id, "Tiempo máximo de ejecución agotado.")
        finally:
            with self.lock:
                self.processes.pop(job_id, None)
                self.futures.pop(job_id, None)
            current = self.store.get("job", job_id)
            if current["status"] in ("cancelled", "failed"):
                workspace = self.store.root / "projects" / current["project_id"] / "runs" / job_id
                for path in workspace.glob("*.parquet"):
                    path.unlink(missing_ok=True)
                (workspace / "dashboard.html").unlink(missing_ok=True)
                shutil.rmtree(workspace / "spill", ignore_errors=True)

    def cancel(self, job_id):
        with self.lock:
            current, changed = self.store.cancel_job(job_id)
            if not changed:
                return current
            process = self.processes.get(job_id)
            if process and process.poll() is None:
                process.terminate()
            future = self.futures.get(job_id)
            if future:
                future.cancel()
        self.store.audit(current["project_id"], "job_cancelled", {"job_id": job_id})
        return self.store.get("job", job_id)

    def close(self):
        self.closed = True
        with self.lock:
            ids = list(self.futures)
        for job_id in ids:
            self.cancel(job_id)
        self.pool.shutdown(wait=True, cancel_futures=True)
