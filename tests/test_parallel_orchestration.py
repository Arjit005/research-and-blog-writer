"""Focused unit and concurrency tests for core.pipeline_runner.

Runs in pure Python without requiring compiled C-extensions (portalocker/pywin32/_rust),
making it deterministic and robust in all execution environments.
"""

import sys
import time
import queue
import threading
import pytest

# Provide mock crew dependency before importing core.pipeline_runner
if "crew" not in sys.modules:
    mock_crew = type(sys)("crew")
    mock_crew.ResearchAndBlogWriter = type("ResearchAndBlogWriter", (), {})
    sys.modules["crew"] = mock_crew

from core.pipeline_runner import PipelineRunner, STAGE_NAMES


def test_stage_progression_both_completion_orders():
    """Verify that completing Stage 2 agents in either order correctly maintains Stage 2 and only advances to Stage 3 when both finish."""
    
    # Case A: Diagram Architect finishes before Blog Post Writer
    q_a = queue.Queue()
    runner_a = PipelineRunner("Test Topic", q_a, {})
    assert runner_a.current_stage == 1

    class MockOutput:
        def __init__(self, role):
            self.agent = type("MockAgent", (), {"role": role})()

    # Task 1 finishes -> advances to Stage 2
    runner_a.task_callback(MockOutput("Senior Researcher"))
    assert runner_a.current_stage == 2

    # Task 2 finishes (Diagram Architect) -> still Stage 2
    runner_a.task_callback(MockOutput("Content Analyst"))
    assert runner_a.current_stage == 2

    # Task 3 finishes (Blog Post Writer) -> advances to Stage 3 (Editorial Reviewer)
    runner_a.task_callback(MockOutput("Blog Post Writer"))
    assert runner_a.current_stage == 3

    # Task 4 finishes (Quality Reviewer) -> completes (Stage 4)
    runner_a.task_callback(MockOutput("Quality Reviewer"))
    assert runner_a.current_stage == 4

    # Case B: Blog Post Writer finishes before Diagram Architect
    q_b = queue.Queue()
    runner_b = PipelineRunner("Test Topic", q_b, {})
    assert runner_b.current_stage == 1

    runner_b.task_callback(MockOutput("Senior Researcher"))
    assert runner_b.current_stage == 2

    # Writer finishes first -> still Stage 2
    runner_b.task_callback(MockOutput("Blog Post Writer"))
    assert runner_b.current_stage == 2

    # Diagram Architect finishes second -> advances to Stage 3
    runner_b.task_callback(MockOutput("Content Analyst"))
    assert runner_b.current_stage == 3

    runner_b.task_callback(MockOutput("Quality Reviewer"))
    assert runner_b.current_stage == 4


def test_concurrent_execution_overlap_and_stage_synchronization():
    """Simulate concurrent threads executing Stage 2 agents and verify time interval overlap and Stage 3 wait."""
    
    event_queue = queue.Queue()
    runner = PipelineRunner("Async Concurrency Topic", event_queue, {})
    
    stage1_finished = False
    stage2_active_agents = set()
    stage2_overlap_detected = False
    stage3_started = False
    lock = threading.Lock()
    
    # 1. Execute Stage 1
    time.sleep(0.02)
    stage1_finished = True
    runner.task_callback(type("T1", (), {"agent": type("A", (), {"role": "Senior Researcher"})()})())
    assert runner.current_stage == 2

    # 2. Concurrently execute Technical Writer and Diagram Architect
    start_barrier = threading.Barrier(2)
    timing_records = {}

    def run_stage2_agent(agent_name: str, delay: float):
        nonlocal stage2_overlap_detected
        start_barrier.wait()  # Synchronized launch
        t_start = time.time()
        with lock:
            assert stage1_finished is True
            assert stage3_started is False
            stage2_active_agents.add(agent_name)
            if len(stage2_active_agents) == 2:
                stage2_overlap_detected = True
        
        # Simulate agent tool work
        runner.step_callback(type("Step", (), {"agent": type("A", (), {"role": agent_name})(), "tool": "Search", "tool_input": "query"})())
        time.sleep(delay)
        
        t_end = time.time()
        timing_records[agent_name] = (t_start, t_end)
        with lock:
            stage2_active_agents.remove(agent_name)
        runner.task_callback(type("T", (), {"agent": type("A", (), {"role": agent_name})()})())

    t_writer = threading.Thread(target=run_stage2_agent, args=("Blog Post Writer", 0.08))
    t_architect = threading.Thread(target=run_stage2_agent, args=("Content Analyst", 0.06))

    t_writer.start()
    t_architect.start()

    t_writer.join()
    t_architect.join()

    # Overlap must be proven
    assert stage2_overlap_detected is True
    writer_start, writer_end = timing_records["Blog Post Writer"]
    architect_start, architect_end = timing_records["Content Analyst"]
    # Check that interval intersection is strictly positive: max(start) < min(end)
    overlap_duration = min(writer_end, architect_end) - max(writer_start, architect_start)
    assert overlap_duration > 0, f"Expected overlapping execution interval, got overlap: {overlap_duration}"

    # Stage 3 starts only now
    assert runner.current_stage == 3
    stage3_started = True
    runner.task_callback(type("T4", (), {"agent": type("A", (), {"role": "Quality Reviewer"})()})())
    assert runner.current_stage == 4


def test_cooperative_cancellation_during_parallel_stage():
    """Verify cooperative cancellation immediately halts execution at step boundary."""
    event_queue = queue.Queue()
    runner = PipelineRunner("Cancellation Topic", event_queue, {})
    runner.request_cancel()
    assert runner.is_cancelled() is True

    with pytest.raises(InterruptedError, match="cancelled"):
        runner.step_callback(type("Step", (), {"agent": type("A", (), {"role": "Blog Post Writer"})(), "tool": "Tool", "tool_input": "test"})())

    with pytest.raises(InterruptedError, match="cancelled"):
        runner.task_callback(type("Task", (), {"agent": type("A", (), {"role": "Content Analyst"})()})())
