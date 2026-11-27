"""Standalone database-backed worker entrypoint for Research Studio.

The database is the durable queue of record. This process polls pending jobs
and uses the same atomic pending-to-running transition as the API worker pool.
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv

load_dotenv(override=False)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("research_worker")

_RUNNING = True


def _handle_signal(signum, _frame) -> None:
    global _RUNNING
    logger.info("Received signal %s; shutting down worker gracefully...", signum)
    _RUNNING = False


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    import database as db
    from backend.routes.research import _execute_run_worker

    db.init_db()
    poll_seconds = max(1.0, float(os.getenv("RESEARCH_WORKER_POLL_SECONDS", "2")))
    logger.info("Research Studio standalone worker started; polling the durable database queue.")
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
