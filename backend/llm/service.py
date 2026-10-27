"""Single-flight local inference, persisted jobs, sanitized failures."""

import threading
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import update

from backend.database import AIAnalysis, utcnow
from backend.llm.contracts import ProviderError


class ReasoningService:
    def __init__(self, sessions, provider):
        self.sessions, self.provider = sessions, provider
        self.lock = threading.BoundedSemaphore(1)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sentinel-ollama")

    def recover(self):
        with self.sessions.begin() as session:
            session.execute(
                update(AIAnalysis)
                .where(AIAnalysis.status == "running")
                .values(
                    status="failed",
                    error="Local inference was interrupted. Request a new analysis.",
                    completed_at=utcnow(),
                )
            )

    def submit(self, job_id: str, model: str, context: dict):
        self.executor.submit(self.run, job_id, model, context)

    def run(self, job_id, model, context):
        try:
            try:
                response = self.provider.reason(model, context).model_dump()
                error = None
            except ProviderError as exc:
                response, error = None, str(exc)
            except Exception:  # noqa: BLE001 -- sanitize third-party failures at the job boundary
                response, error = None, "Local reasoning failed unexpectedly. No model output was accepted."
            with self.sessions.begin() as session:
                job = session.get(AIAnalysis, job_id)
                job.response, job.error = response, error
                job.status, job.completed_at = "failed" if error else "completed", utcnow()
        finally:
            self.lock.release()

    def close(self):
        self.executor.shutdown(wait=True)
