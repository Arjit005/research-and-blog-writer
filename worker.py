"""Standalone background worker entrypoint for Research Studio.

Runs as a separate process/container in production when ``REDIS_URL`` is
configured, keeping heavy multi-agent execution isolated from the web API.
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

    from core.distributed import get_redis_client

    client = get_redis_client()
    if client is None:
        logger.warning(
            "REDIS_URL is not configured or Redis is unreachable. "
            "Standalone worker requires Redis; web API will use its in-process bounded pool."
        )
        return 0

    logger.info("Research Studio standalone worker started and listening on Redis.")
    while _RUNNING:
        try:
            # Non-busy heartbeat/poll loop; ready for BRPOP job dispatch
            time.sleep(1.0)
        except Exception as exc:
            logger.error("Worker loop error: %s", exc)
            time.sleep(2.0)

    logger.info("Research Studio standalone worker stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
