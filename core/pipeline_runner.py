"""Thread-safe pipeline runner for CrewAI with queue event emission.

The runner executes the 4-agent crew in a background thread and emits
sequenced events to a thread-safe queue consumed by the UI.  Stage ids are
aligned with the crew's agent roles (``crew.py``) and only advance when a task
actually completes successfully — a failure no longer looks like a completed
stage.

Cancellation is cooperative: :meth:`PipelineRunner.request_cancel` sets a
threading event, and the crew's step/task callbacks raise ``InterruptedError``
so the run stops at the next agent boundary.
"""

from __future__ import annotations

import time
import queue
import logging
import threading
from contextlib import ExitStack
from typing import Any, Dict, Optional

from crew import ResearchAndBlogWriter

logger = logging.getLogger(__name__)

# Must stay aligned with the @agent role names in crew.py.
STAGE_NAMES = [
    "Senior Researcher",
    "Content Analyst",
    "Blog Post Writer",
    "Quality Reviewer",
]


class PipelineRunner:
    """Manages the background execution of the 4-agent crew, safely emitting events to a thread-safe Queue."""

    def __init__(
        self,
        topic: str,
        event_queue: queue.Queue,
        result_container: Dict[str, Any],
        cancel_event: Optional[threading.Event] = None,
        runtime_keys: Optional[Dict[str, str]] = None,
    ):
        self.topic = topic
        self.event_queue = event_queue
        self.result_container = result_container
        self.cancel_event = cancel_event or threading.Event()
        self.runtime_keys = runtime_keys or {}
        self.current_stage = 1

    # -- cancellation ------------------------------------------------------
    def request_cancel(self) -> None:
        """Request cooperative cancellation of the running crew."""
        self.cancel_event.set()

    def is_cancelled(self) -> bool:
        """Return True if cancellation has been requested or the run timed out."""
        return self.cancel_event.is_set()

    def _raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise InterruptedError("Research run was cancelled by user or timeout.")

    @property
    def current_stage_name(self) -> str:
        index = max(0, min(self.current_stage - 1, len(STAGE_NAMES) - 1))
        return STAGE_NAMES[index]

    # -- crew callbacks ----------------------------------------------------
    def step_callback(self, step_output: Any) -> None:
        """Invoked by CrewAI after each intermediate agent tool execution or thought."""
        self._raise_if_cancelled()
        try:
            detail = ""
            if hasattr(step_output, "tool"):
                tool_name = getattr(step_output, "tool", "Tool")
                tool_input = str(getattr(step_output, "tool_input", ""))[:60]
                detail = f"Running {tool_name} ({tool_input})"
            elif hasattr(step_output, "text") and step_output.text:
                detail = str(step_output.text).strip()[:80]
            elif isinstance(step_output, tuple) and len(step_output) > 0:
                first = step_output[0]
                tool = getattr(first, "tool", "")
                if tool:
                    detail = f"Using {tool}"
            elif isinstance(step_output, str):
                detail = step_output.strip()[:80]

            if detail:
                self.event_queue.put({
                    "type": "step",
                    "stage_id": self.current_stage,
                    "stage_name": self.current_stage_name,
                    "detail": detail,
                    "timestamp": time.time(),
                })
        except InterruptedError:
            raise
        except Exception as e:
            logger.debug(f"Error in step_callback: {e}")

    def task_callback(self, task_output: Any) -> None:
        """Invoked by CrewAI when a task finishes successfully."""
        self._raise_if_cancelled()
        try:
            self.event_queue.put({
                "type": "task_done",
                "stage_id": self.current_stage,
                "stage_name": self.current_stage_name,
                "timestamp": time.time(),
            })
            # Advance only after a successful task; never beyond the last stage.
            self.current_stage = min(self.current_stage + 1, len(STAGE_NAMES))
        except InterruptedError:
            raise
        except Exception as e:
            logger.debug(f"Error in task_callback: {e}")

    # -- execution ---------------------------------------------------------
    def _emit_cancelled(self) -> None:
        self.result_container["cancelled"] = True
        self.event_queue.put({
            "type": "cancelled",
            "stage_id": self.current_stage,
            "stage_name": self.current_stage_name,
            "message": "Research run was cancelled before completion.",
            "timestamp": time.time(),
        })

    def run(self) -> None:
        """Target function executed inside a dedicated background thread."""
        start_time = time.time()
        self.event_queue.put({
            "type": "run_start",
            "timestamp": start_time,
        })

        try:
            with ExitStack() as stack:
                # Runtime-scoped credentials (never mutate os.environ globally).
                openrouter_key = self.runtime_keys.get("openrouter")
                gemini_key = self.runtime_keys.get("gemini")
                serper_key = self.runtime_keys.get("serper")
                if openrouter_key or gemini_key:
                    from llm_fallback import scoped_llm_keys

                    stack.enter_context(scoped_llm_keys(openrouter_key=openrouter_key, gemini_key=gemini_key))
                if serper_key:
                    from tools.search_tool import scoped_serper_key

                    stack.enter_context(scoped_serper_key(serper_key))

                crew_instance = ResearchAndBlogWriter()
                crew_obj = crew_instance.crew(
                    step_callback=self.step_callback,
                    task_callback=self.task_callback,
                )
                result = crew_obj.kickoff(inputs={"topic": self.topic})

            self._raise_if_cancelled()
            self.result_container["result"] = result
            self.result_container["elapsed"] = round(time.time() - start_time, 2)
            self.event_queue.put({
                "type": "run_done",
                "timestamp": time.time(),
            })
        except InterruptedError:
            logger.info("Pipeline runner cancelled at stage %s", self.current_stage)
            self._emit_cancelled()
        except Exception as e:
            logger.exception("Pipeline runner encountered an error")
            self.result_container["error"] = str(e)
            self.event_queue.put({
                "type": "error",
                "stage_id": self.current_stage,
                "stage_name": self.current_stage_name,
                "message": str(e),
                "timestamp": time.time(),
            })
