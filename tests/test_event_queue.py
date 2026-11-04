"""Unit tests for Stepper Event Reducer and thread-safe queue draining."""

import time
import queue
import threading
import pytest
from ui.stepper import init_stepper_state, reduce_stepper_event, render_stepper_html


def test_init_stepper_state():
    """Verify clean initial state with 4 pending stages."""
    state = init_stepper_state()
    assert state["active_stage"] == 0
    assert state["is_finished"] is False
    assert state["has_error"] is False
    assert len(state["stages"]) == 4
    for i in range(1, 5):
        assert state["stages"][i]["status"] == "pending"


def test_pure_reducer_linear_progression():
    """Verify that a sequence of events advances stages correctly."""
    state = init_stepper_state()
    t0 = 1000.0

    # 1. Run start
    state = reduce_stepper_event(state, {"type": "run_start", "timestamp": t0})
    assert state["active_stage"] == 1
    assert state["stages"][1]["status"] == "running"
    assert state["stages"][2]["status"] == "pending"

    # 2. Step in stage 1
    state = reduce_stepper_event(state, {"type": "step", "stage_id": 1, "detail": "Searching DuckDuckGo"})
    assert state["stages"][1]["detail"] == "Searching DuckDuckGo"

    # 3. Task 1 done -> stage 1 done, stage 2 running
    state = reduce_stepper_event(state, {"type": "task_done", "stage_id": 1, "timestamp": t0 + 15.0})
    assert state["stages"][1]["status"] == "done"
    assert state["stages"][1]["duration_sec"] == 15.0
    assert state["active_stage"] == 2
    assert state["stages"][2]["status"] == "running"

    # 4. Task 2 done -> stage 2 done, stage 3 running
    state = reduce_stepper_event(state, {"type": "task_done", "stage_id": 2, "timestamp": t0 + 30.0})
    assert state["stages"][2]["status"] == "done"
    assert state["stages"][2]["duration_sec"] == 15.0
    assert state["active_stage"] == 3
    assert state["stages"][3]["status"] == "running"

    # 5. Task 3 done -> stage 3 done, stage 4 running
    state = reduce_stepper_event(state, {"type": "task_done", "stage_id": 3, "timestamp": t0 + 50.0})
    assert state["stages"][3]["status"] == "done"
    assert state["active_stage"] == 4
    assert state["stages"][4]["status"] == "running"

    # 6. Task 4 done -> all done
    state = reduce_stepper_event(state, {"type": "task_done", "stage_id": 4, "timestamp": t0 + 65.0})
    assert state["stages"][4]["status"] == "done"
    assert state["is_finished"] is True


def test_pure_reducer_error_handling():
    """Verify that error event marks the active stage failed and records error message."""
    state = init_stepper_state()
    state = reduce_stepper_event(state, {"type": "run_start", "timestamp": 1000.0})
    state = reduce_stepper_event(state, {"type": "task_done", "stage_id": 1, "timestamp": 1010.0})

    # Error during stage 2
    err_event = {
        "type": "error",
        "stage_id": 2,
        "message": "LLM 429 Rate Limit Exhausted",
        "timestamp": 1015.0
    }
    state = reduce_stepper_event(state, err_event)

    assert state["has_error"] is True
    assert "429 Rate Limit" in state["error_message"]
    assert state["stages"][2]["status"] == "error"
    assert state["stages"][3]["status"] == "pending"


def test_drain_loop_with_simulated_thread():
    """Verify that draining the queue catches every single event until thread termination."""
    event_q = queue.Queue()
    state = init_stepper_state()

    def fake_worker():
        event_q.put({"type": "run_start", "timestamp": time.time()})
        time.sleep(0.05)
        event_q.put({"type": "step", "stage_id": 1, "detail": "Simulated search"})
        time.sleep(0.05)
        event_q.put({"type": "task_done", "stage_id": 1, "timestamp": time.time()})
        event_q.put({"type": "run_done", "timestamp": time.time()})

    worker_thread = threading.Thread(target=fake_worker)
    worker_thread.start()

    # Drain loop matching the main script pattern
    while worker_thread.is_alive() or not event_q.empty():
        try:
            event = event_q.get_nowait()
            state = reduce_stepper_event(state, event)
        except queue.Empty:
            time.sleep(0.02)

    worker_thread.join()
    assert state["stages"][1]["status"] == "done"
    assert state["is_finished"] is True


def test_render_stepper_html():
    """Verify generated HTML structure contains all 4 stages and responsive classes."""
    state = init_stepper_state()
    state = reduce_stepper_event(state, {"type": "run_start", "timestamp": 100.0})
    html_out = render_stepper_html(state)

    assert "stepper-container" in html_out
    assert "Senior Researcher" in html_out
    assert "Systems Analyst" in html_out
    assert "Lead Author" in html_out
    assert "Quality Reviewer" in html_out
    assert "stage-running" in html_out
    assert "prefers-reduced-motion" in html_out
