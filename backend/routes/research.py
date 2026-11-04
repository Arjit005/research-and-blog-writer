"""Research Runs API endpoints (Job Model, Background Execution & Resumable SSE Stream)."""

from __future__ import annotations

import os
import json
import time
import uuid
import asyncio
import logging
import threading
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request, status
from fastapi.responses import StreamingResponse

import database as db
from backend.deps import get_current_user
from backend.schemas import CreateRunRequest, RunResponse, RunStatusResponse
from llmops.tracing import LangSmithJobTracer, export_failure_to_dataset
from llmops.telemetry import calculate_readability, estimate_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["Research Runs"])

_CANCELLATION_EVENTS: Dict[str, threading.Event] = {}


def _execute_run_worker(
    run_id: str,
    topic: str,
    user_id: int,
    tone: Optional[str],
    audience: Optional[str],
    target_length: Optional[str],
):
    """Background worker executing CrewAI pipeline and storing sequenced events."""
    cancel_event = threading.Event()
    _CANCELLATION_EVENTS[run_id] = cancel_event

    tracer = LangSmithJobTracer(
        run_id=run_id,
        topic=topic,
        user_id=user_id,
        tone=tone,
        audience=audience,
        target_length=target_length,
    )

    stage_names = [
        "Senior Research Analyst",
        "Content Strategist & Outliner",
        "Technical Writer & Storyteller",
        "Senior Editor & Visual Architect",
    ]
    current_stage_idx = 0
    tracer.start_span("stage_0", f"CrewAI Stage: {stage_names[0]}", run_type="chain")

    try:
        db.update_research_job(run_id, status="running")
        db.append_job_event(run_id, "status", {"status": "running", "stage": "Initializing multi-agent squad..."})

        # Dynamic imports to avoid loading crew in pure tests if not invoked
        from crew import ResearchAndBlogWriter
        from core.mermaid_split import extract_mermaid

        def on_step(step_output: Any) -> None:
            if cancel_event.is_set():
                raise InterruptedError("Research run was cancelled by user.")
            detail = ""
            if hasattr(step_output, "tool"):
                tool_name = getattr(step_output, "tool", "Tool")
                tool_input = str(getattr(step_output, "tool_input", ""))[:60]
                detail = f"Running {tool_name} ({tool_input})"
            elif hasattr(step_output, "text") and step_output.text:
                detail = str(step_output.text).strip()[:80]
            elif isinstance(step_output, str):
                detail = step_output.strip()[:80]

            if detail:
                db.append_job_event(run_id, "step", {"detail": detail, "timestamp": time.time()})

        def on_task(task_output: Any) -> None:
            if cancel_event.is_set():
                raise InterruptedError("Research run was cancelled by user.")
            nonlocal current_stage_idx
            db.append_job_event(run_id, "task_done", {"timestamp": time.time()})
            tracer.end_span(f"stage_{current_stage_idx}")
            current_stage_idx += 1
            if current_stage_idx < len(stage_names):
                tracer.start_span(f"stage_{current_stage_idx}", f"CrewAI Stage: {stage_names[current_stage_idx]}", run_type="chain")

        start_time = time.time()
        crew_instance = ResearchAndBlogWriter()
        crew_obj = crew_instance.crew(step_callback=on_step, task_callback=on_task)
        result = crew_obj.kickoff(inputs={"topic": topic})

        # Check if cancelled while kickoff was executing
        current_job = db.get_research_job(run_id)
        if current_job and current_job.get("status") == "cancelled":
            tracer.end_job(outputs={"status": "cancelled"})
            return

        elapsed = round(time.time() - start_time, 2)
        raw_content = str(result.raw) if hasattr(result, "raw") else str(result)
        clean_content, mermaid_code = extract_mermaid(raw_content)

        art_id = db.save_article(
            topic=topic,
            content=clean_content,
            tone=tone,
            audience=audience,
            target_length=target_length,
            generation_time=elapsed,
            user_id=user_id,
        )

        db.save_article_revision(
            article_id=art_id,
            content=clean_content,
            summary="Initial AI Squad Generation",
            author="AI Squad",
            user_id=user_id,
        )

        readability = calculate_readability(clean_content)
        tracer.log_evaluation("flesch_reading_ease", readability.get("score", 0.0), comment=readability.get("grade"))

        trace_url = tracer.end_job(outputs={
            "article_id": art_id,
            "word_count": len(clean_content.split()),
            "elapsed_sec": elapsed,
            "readability_score": readability.get("score", 0.0),
        })

        telemetry_data = {
            "topic": topic,
            "duration_sec": elapsed,
            "tokens_estimated": estimate_tokens(clean_content),
            "models_used": ["openrouter/google/gemini-2.5-flash"],
            "fallback_count": 0,
            "fallback_events": [],
            "readability": readability,
            "trace_url": trace_url,
        }
        db.save_telemetry_run(article_id=art_id, telemetry_data=telemetry_data, user_id=user_id)

        db.update_research_job(run_id, status="completed", result_article_id=art_id, trace_url=trace_url)
        db.append_job_event(run_id, "completed", {
            "status": "completed",
            "article_id": art_id,
            "topic": topic,
            "word_count": len(clean_content.split()),
            "elapsed_sec": elapsed,
            "trace_url": trace_url,
        })
    except Exception as e:
        logger.exception(f"Run worker error on run {run_id}: {e}")
        tracer.end_job(error=str(e))
        export_failure_to_dataset("production_failures", topic, str(e), metadata={"run_id": run_id, "user_id": user_id})
        db.update_research_job(run_id, status="failed", error_message=str(e))
        db.append_job_event(run_id, "error", {"message": str(e), "timestamp": time.time()})
    finally:
        _CANCELLATION_EVENTS.pop(run_id, None)


@router.post("", response_model=RunResponse)
def create_research_run(
    body: CreateRunRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> RunResponse:
    """Launch a durable research job. Enforces 1 active run per user."""
    # 1. Enforce single concurrent run per user
    active_job = db.get_active_user_job(user["id"])
    if active_job:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a research run in progress (ID: {active_job['run_id']}). Wait for it to complete or cancel it.",
        )

    # 2. Generate run ID and initialize job in DB
    run_id = f"run_{uuid.uuid4().hex}"
    db.create_research_job(
        run_id=run_id,
        topic=body.topic,
        user_id=user["id"],
        tone=body.tone,
        audience=body.audience,
        target_length=body.target_length,
    )

    db.append_job_event(run_id, "run_start", {"run_id": run_id, "topic": body.topic, "timestamp": time.time()})

    # 3. Spawn background thread
    worker_thread = threading.Thread(
        target=_execute_run_worker,
        args=(run_id, body.topic, user["id"], body.tone, body.audience, body.target_length),
        daemon=True,
    )
    worker_thread.start()

    return RunResponse(run_id=run_id, status="running", topic=body.topic)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run_status(
    run_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> RunStatusResponse:
    """Check current status and results of a research run."""
    job = db.get_research_job(run_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found.")

    return RunStatusResponse(
        run_id=job["run_id"],
        status=job["status"],
        topic=job["topic"],
        result_article_id=job.get("result_article_id"),
        error_message=job.get("error_message"),
        trace_url=job.get("trace_url"),
        created_at=str(job.get("created_at", "")),
        updated_at=str(job.get("updated_at", "")),
    )


@router.get("/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    after_seq: Optional[int] = Query(0),
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Resumable Server-Sent Events (SSE) stream delivering sequenced execution events.

    Supports 'Last-Event-ID' header or '?after_seq=' query param for seamless reconnection.
    Emits ': ping\\n\\n' heartbeats every 15s to prevent intermediary proxy timeouts.
    """
    job = db.get_research_job(run_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found.")

    start_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else (after_seq or 0)

    async def event_generator():
        current_seq = start_seq
        last_heartbeat = time.time()

        while True:
            if await request.is_disconnected():
                break

            events = await asyncio.to_thread(db.get_job_events, run_id, after_seq_id=current_seq)
            if events:
                for ev in events:
                    seq_id = ev["seq_id"]
                    ev_type = ev["event_type"]
                    payload = json.dumps(ev["payload"]) if not isinstance(ev["payload"], str) else ev["payload"]
                    yield f"id: {seq_id}\nevent: {ev_type}\ndata: {payload}\n\n"
                    current_seq = max(current_seq, seq_id)
                last_heartbeat = time.time()

            # Check job terminal status
            j = await asyncio.to_thread(db.get_research_job, run_id)
            if j and j.get("status") in ("completed", "failed", "cancelled"):
                # Deliver any remaining events then close stream
                more = await asyncio.to_thread(db.get_job_events, run_id, after_seq_id=current_seq)
                if not more:
                    break

            # Heartbeat to keep connection alive
            if time.time() - last_heartbeat >= 15:
                yield ": ping\n\n"
                last_heartbeat = time.time()

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{run_id}/cancel")
def cancel_research_run(
    run_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Request graceful cancellation of an active research run."""
    job = db.get_research_job(run_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found.")

    if job["status"] in ("completed", "failed", "cancelled"):
        return {"success": False, "message": f"Run already in terminal state: {job['status']}"}

    # Signal active background worker to halt immediately
    cancel_event = _CANCELLATION_EVENTS.get(run_id)
    if cancel_event:
        cancel_event.set()

    db.update_research_job(run_id, status="cancelled")
    db.append_job_event(run_id, "cancelled", {"message": "Run was cancelled by user."})
    return {"success": True, "message": "Research run marked as cancelled."}
