"""Bounded task queue abstraction for background research runs.

Replaces unbounded ad-hoc daemon thread spawning with a bounded worker pool
(ThreadPoolExecutor) so concurrent runs cannot exhaust server CPU/memory.
"""

from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        val = int(os.getenv(name, default))
        return max(1, val)
    except (TypeError, ValueError):
        return default


_WORKER_CONCURRENCY = _env_int("RESEARCH_WORKER_CONCURRENCY", 4)
_executor: Optional[ThreadPoolExecutor] = None
_executor_lock = threading.Lock()


def get_worker_executor() -> ThreadPoolExecutor:
    """Return the shared bounded ThreadPoolExecutor for background research runs."""
    global _executor
    if _executor is None:
        with _executor_lock:
            if _executor is None:
                _executor = ThreadPoolExecutor(
                    max_workers=_WORKER_CONCURRENCY,
                    thread_name_prefix="research-worker",
                )
                logger.info(
                    "Initialized bounded research worker pool (max_workers=%d).",
                    _WORKER_CONCURRENCY,
                )
    return _executor


def enqueue_research_run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Future:
    """Submit a research run to the bounded background worker pool."""
    executor = get_worker_executor()
    return executor.submit(fn, *args, **kwargs)
