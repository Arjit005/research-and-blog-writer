"""Dedicated database-backed worker entrypoint for research jobs."""

from __future__ import annotations

import logging
import os
import shutil
import signal
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=False)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("research_worker")

_RUNNING = True


def _cleanup_terminal_checkpoints(db) -> None:
    """Remove checkpoint folders for jobs already in a terminal state."""
    root = Path(os.getenv("RESEARCH_CHECKPOINT_DIR", ".research_checkpoints")).expanduser()
    if not root.is_dir():
        return
    for directory in root.iterdir():
        if not directory.is_dir():
            continue
        try:
            job = db.get_research_job(directory.name)
            if job and job.get("status") in {"completed", "failed", "cancelled"}:
                shutil.rmtree(directory, ignore_errors=True)
        except Exception:
            logger.debug("Could not inspect old checkpoint folder %s", directory, exc_info=True)


def _handle_signal(signum, _frame) -> None:
    global _RUNNING
    logger.info("Received signal %s; shutting down worker gracefully...", signum)
    _RUNNING = False


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if os.getenv("RESEARCH_WORKER_MODE", "false").strip().lower() in {"1", "true", "yes", "on"} and not os.getenv("TIDB_HOST"):
        logger.critical("RESEARCH_WORKER_MODE requires the same shared TiDB credentials as the API service.")
        return 2

    import database as db
    from backend.routes.research import _execute_run_worker

    db.init_db()
    recovered = db.recover_interrupted_jobs(stale_after_seconds=120, resume_checkpointed=True)
    if recovered:
        logger.warning("Recovered %s interrupted research job(s).", recovered)
    _cleanup_terminal_checkpoints(db)
    poll_seconds = max(1.0, float(os.getenv("RESEARCH_WORKER_POLL_SECONDS", "2")))
    logger.info("Research Studio worker started; polling the durable database queue.")
    while _RUNNING:
        try:
            pending_jobs = db.get_pending_research_jobs()
            if not pending_jobs:
                time.sleep(poll_seconds)
                continue
            for job in pending_jobs:
                if not _RUNNING:
                    break
                logger.info("Claiming pending research job %s", job["run_id"])
                _execute_run_worker(
                    job["run_id"], job["topic"], job.get("user_id") or 0,
                    job.get("tone"), job.get("audience"), job.get("target_length"),
                )
        except Exception as exc:
            logger.error("Worker loop error: %s", exc)
            time.sleep(poll_seconds)

    logger.info("Research Studio standalone worker stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
