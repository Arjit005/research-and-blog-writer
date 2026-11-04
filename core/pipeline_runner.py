"""Thread-safe pipeline runner for CrewAI with queue event emission."""

from __future__ import annotations

import time
import queue
import logging
from typing import Any, Dict, Optional
from crew import ResearchAndBlogWriter

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Manages the background execution of the 4-agent crew, safely emitting events to a thread-safe Queue."""

    def __init__(self, topic: str, event_queue: queue.Queue, result_container: Dict[str, Any]):
        self.topic = topic
        self.event_queue = event_queue
        self.result_container = result_container
        self.current_stage = 1

    def step_callback(self, step_output: Any) -> None:
        """Invoked by CrewAI after each intermediate agent tool execution or thought."""
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
                    "detail": detail,
                    "timestamp": time.time(),
                })
        except Exception as e:
            logger.debug(f"Error in step_callback: {e}")

    def task_callback(self, task_output: Any) -> None:
        """Invoked by CrewAI when a task finishes."""
        try:
            self.event_queue.put({
                "type": "task_done",
                "stage_id": self.current_stage,
                "timestamp": time.time(),
            })
            self.current_stage += 1
        except Exception as e:
            logger.debug(f"Error in task_callback: {e}")

    def run(self) -> None:
        """Target function executed inside a dedicated background thread."""
        start_time = time.time()
        self.event_queue.put({
            "type": "run_start",
            "timestamp": start_time,
        })

        try:
            crew_instance = ResearchAndBlogWriter()
            crew_obj = crew_instance.crew(
                step_callback=self.step_callback,
                task_callback=self.task_callback,
            )
            result = crew_obj.kickoff(inputs={"topic": self.topic})
            self.result_container["result"] = result
            self.result_container["elapsed"] = round(time.time() - start_time, 2)
            self.event_queue.put({
                "type": "run_done",
                "timestamp": time.time(),
            })
        except Exception as e:
            logger.exception("Pipeline runner encountered an error")
            self.result_container["error"] = str(e)
            self.event_queue.put({
                "type": "error",
                "stage_id": self.current_stage,
                "message": str(e),
                "timestamp": time.time(),
            })
