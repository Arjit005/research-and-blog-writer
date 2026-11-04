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
from security.guardrails import mask_pii_and_secrets, validate_user_input

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runs", tags=["Research Runs"])

_CANCELLATION_EVENTS: Dict[str, threading.Event] = {}

# Event types that close an SSE stream (only after they have been delivered).
_TERMINAL_EVENT_TYPES = frozenset({"completed", "error", "cancelled"})
_TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled"})

GENERIC_SECURITY_REJECTION = "Run request rejected by security policy."


# ---------------------------------------------------------------------------
# Guarded LLM usage telemetry (optional dependency)
# ---------------------------------------------------------------------------

def _reset_llm_usage_stats() -> None:
    """Reset module-level fallback LLM usage counters if the module is available."""
    try:
        import llm_fallback  # optional dependency (imports crewai)

        reset_fn = getattr(llm_fallback, "reset_usage_stats", None)
        if callable(reset_fn):
            reset_fn()
    except Exception as exc:  # pragma: no cover - depends on optional deps
        logger.debug("LLM usage stats reset unavailable: %s", exc)


def _get_llm_usage_stats() -> Optional[Dict[str, Any]]:
    """Return real fallback-LLM usage stats, or None when unavailable."""
    try:
        import llm_fallback  # optional dependency (imports crewai)

        getter = getattr(llm_fallback, "get_usage_stats", None)
        if callable(getter):
            stats = getter()
            if isinstance(stats, dict):
                return stats
    except Exception as exc:  # pragma: no cover - depends on optional deps
        logger.debug("LLM usage stats unavailable: %s", exc)
    return None


def _build_telemetry_data(
    topic: str,
    elapsed: float,
    clean_content: str,
    readability: Dict[str, Any],
    trace_url: Optional[str],
    usage_stats: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build honest telemetry from real fallback-LLM usage (never hardcoded models)."""
    stats = usage_stats if isinstance(usage_stats, dict) else {}
    models_used = [str(m) for m in (stats.get("models_used") or []) if m]
    failed_models = [str(m) for m in (stats.get("failed_models") or []) if m]
    fallback_events = stats.get("fallback_events") or []
    if not isinstance(fallback_events, list):
        fallback_events = []
    try:
        call_count = int(stats.get("call_count") or 0)
    except (TypeError, ValueError):
        call_count = 0

    return {
        "topic": topic,
        "duration_sec": elapsed,
        "tokens_estimated": estimate_tokens(clean_content),
        "models_used": models_used,
        "failed_models": failed_models,
        "call_count": call_count,
        # Derived from the real fallback event log (no hardcoded zero/lie).
        "fallback_count": len(fallback_events),
        "fallback_events": fallback_events,
        "readability": readability,
        "trace_url": trace_url,
    }


# ---------------------------------------------------------------------------
# Worker helpers
# ---------------------------------------------------------------------------

def _job_is_cancelled(run_id: str, cancel_event: threading.Event) -> bool:
    """Check cancellation via the in-memory event *and* the durable DB status.

    The in-memory event only exists inside the process that owns the worker; the
    durable status check closes the gap where a cancel request races stage
    boundaries (and would otherwise keep a cancelled job running to completion).
    """
    if cancel_event.is_set():
        return True
    try:
        job = db.get_research_job(run_id)
    except Exception as exc:  # pragma: no cover - DB failure should not abort work
        logger.warning("Cancellation status check failed for run %s: %s", run_id, exc)
        return False
    return bool(job and job.get("status") == "cancelled")


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
        # Defense in depth: the API validates the topic before enqueueing, but a
        # job row could also come from a different/internal producer.
        is_safe, safe_topic = validate_user_input(topic)
        if not is_safe:
            try:
                db.save_security_event(
                    "PROMPT_INJECTION_BLOCKED",
                    {"endpoint": "run_worker", "run_id": run_id},
                    user_id=user_id,
                )
            except Exception:
                pass
            raise ValueError(GENERIC_SECURITY_REJECTION)

        # Write status last on completion; here it is a start transition only.
        db.update_research_job(run_id, status="running")
        db.append_job_event(run_id, "status", {"status": "running", "stage": "Initializing multi-agent squad..."})

        # Dynamic imports to avoid loading crew in pure tests if not invoked
        from crew import ResearchAndBlogWriter
        try:
            from core.mermaid_split import extract_mermaid
        except ImportError:
            import sys
            from pathlib import Path
            _root = str(Path(__file__).resolve().parent.parent.parent)
            if _root not in sys.path:
                sys.path.insert(0, _root)
            _parent = str(Path(__file__).resolve().parent.parent)
            if _parent not in sys.path:
                sys.path.insert(0, _parent)
            try:
                from core.mermaid_split import extract_mermaid
            except ImportError:
                def extract_mermaid(content: str):
                    import re
                    m = re.search(r"```mermaid\s*([\s\S]*?)```", content or "", re.IGNORECASE)
                    return content or "", (m.group(1).strip() if m else "")

        def _raise_if_cancelled() -> None:
            if _job_is_cancelled(run_id, cancel_event):
                raise InterruptedError("Research run was cancelled by user.")

        def on_step(step_output: Any) -> None:
            _raise_if_cancelled()
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
                # SSE step details are user-visible: mask PII/secrets before storing.
                safe_detail = mask_pii_and_secrets(detail)[:100]
                db.append_job_event(run_id, "step", {"detail": safe_detail, "timestamp": time.time()})

        def on_task(task_output: Any) -> None:
            _raise_if_cancelled()
            nonlocal current_stage_idx
            db.append_job_event(run_id, "task_done", {"timestamp": time.time()})
            tracer.end_span(f"stage_{current_stage_idx}")
            current_stage_idx += 1
            if current_stage_idx < len(stage_names):
                tracer.start_span(f"stage_{current_stage_idx}", f"CrewAI Stage: {stage_names[current_stage_idx]}", run_type="chain")

        # Resolve API keys: user-specific credentials take precedence over environment
        user_keys = db.get_user_api_keys(user_id=user_id) if (user_id and hasattr(db, "get_user_api_keys")) else {}
        u_gemini = user_keys.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
        u_openrouter = user_keys.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY")

        from llm_fallback import scoped_llm_keys

        with scoped_llm_keys(openrouter_key=u_openrouter, gemini_key=u_gemini):
            start_time = time.time()
            _reset_llm_usage_stats()
            crew_instance = ResearchAndBlogWriter()
            crew_obj = crew_instance.crew(step_callback=on_step, task_callback=on_task)
            result = crew_obj.kickoff(inputs={"topic": safe_topic})
            usage_stats = _get_llm_usage_stats()

        # Check if cancelled while kickoff was executing
        if _job_is_cancelled(run_id, cancel_event):
            tracer.end_job(outputs={"status": "cancelled"})
            return

        elapsed = round(time.time() - start_time, 2)
        raw_content = str(result.raw) if hasattr(result, "raw") else str(result)
        clean_content, mermaid_code = extract_mermaid(raw_content)
        # Mask PII / secrets before persisting anything user-visible.
        clean_content = mask_pii_and_secrets(clean_content)

        art_id, _initial_revision_num = db.save_article_with_initial_revision(
            topic=safe_topic,
            content=clean_content,
            tone=tone,
            audience=audience,
            target_length=target_length,
            generation_time=elapsed,
            user_id=user_id,
            summary="Initial AI Squad Generation",
            author="AI Squad",
        )

        readability = calculate_readability(clean_content)
        tracer.log_evaluation("flesch_reading_ease", readability.get("score", 0.0), comment=readability.get("grade"))

        trace_url = tracer.end_job(outputs={
            "article_id": art_id,
            "word_count": len(clean_content.split()),
            "elapsed_sec": elapsed,
            "readability_score": readability.get("score", 0.0),
        })

        telemetry_data = _build_telemetry_data(
            topic=safe_topic,
            elapsed=elapsed,
            clean_content=clean_content,
            readability=readability,
            trace_url=trace_url,
            usage_stats=usage_stats,
        )
        try:
            db.save_telemetry_run(article_id=art_id, telemetry_data=telemetry_data, user_id=user_id)
        except Exception as exc:  # telemetry is best-effort; never fail a finished article
            logger.warning("Telemetry persistence failed for run %s: %s", run_id, exc)

        # Ordering guarantee: append the terminal SSE event BEFORE flipping the job
        # to a terminal status, so a stream that observes the terminal status can
        # always flush the terminal event first (no lost event on reconnect).
        db.append_job_event(run_id, "completed", {
            "status": "completed",
            "article_id": art_id,
            "topic": safe_topic,
            "word_count": len(clean_content.split()),
            "elapsed_sec": elapsed,
            "trace_url": trace_url,
        })
        db.update_research_job(run_id, status="completed", result_article_id=art_id, trace_url=trace_url)
    except Exception as e:
        logger.exception(f"Run worker error on run {run_id}: {e}")
        # If the job was cancelled concurrently, the cancel endpoint already wrote
        # the terminal event/status: never resurrect or duplicate a terminal state.
        try:
            current_job = db.get_research_job(run_id)
        except Exception:
            current_job = None
        if current_job and current_job.get("status") == "cancelled":
            tracer.end_job(outputs={"status": "cancelled"})
            return

        err_text = str(e)
        if "free-models-per-day" in err_text or ("429" in err_text and "openrouter" in err_text.lower()):
            safe_error = (
                "OpenRouter free-tier daily rate limit reached (50 requests/day). "
                "Please configure a free Google Gemini API Key in Settings (⚙️ API Keys at top right) "
                "to get 1,500 requests per day for free on Google AI Studio."
            )
        else:
            safe_error = mask_pii_and_secrets(err_text)
        tracer.end_job(error=safe_error)
        try:
            export_failure_to_dataset("production_failures", topic, safe_error, metadata={"run_id": run_id, "user_id": user_id})
        except Exception:
            pass
        db.append_job_event(run_id, "error", {"message": safe_error, "timestamp": time.time()})
        db.update_research_job(run_id, status="failed", error_message=safe_error)
    finally:
        _CANCELLATION_EVENTS.pop(run_id, None)


@router.post("", response_model=RunResponse)
def create_research_run(
    body: CreateRunRequest,
    user: Dict[str, Any] = Depends(get_current_user),
) -> RunResponse:
    """Launch a durable research job. Enforces 1 active run per user."""
    # 0. Guardrail: validate the untrusted topic before it reaches any agent/LLM.
    is_safe, safe_or_message = validate_user_input(body.topic)
    if not is_safe:
        try:
            db.save_security_event(
                "PROMPT_INJECTION_BLOCKED",
                {"endpoint": "create_run", "topic_preview": body.topic[:120]},
                user_id=user["id"],
            )
        except Exception as exc:  # pragma: no cover - audit best effort
            logger.warning("Failed to record security event: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=GENERIC_SECURITY_REJECTION,
        )
    topic = safe_or_message

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
        topic=topic,
        user_id=user["id"],
        tone=body.tone,
        audience=body.audience,
        target_length=body.target_length,
    )

    db.append_job_event(run_id, "run_start", {"run_id": run_id, "topic": topic, "timestamp": time.time()})

    # 3. Spawn background thread
    worker_thread = threading.Thread(
        target=_execute_run_worker,
        args=(run_id, topic, user["id"], body.tone, body.audience, body.target_length),
        daemon=True,
    )
    worker_thread.start()

    return RunResponse(run_id=run_id, status="running", topic=topic)


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

    The stream only closes after the terminal event (``completed``/``error``/
    ``cancelled``) has been yielded, so clients cannot miss the final state even
    when they reconnect after the job already finished.
    """
    job = db.get_research_job(run_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Research run not found.")

    start_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else (after_seq or 0)

    async def event_generator():
        current_seq = start_seq
        last_heartbeat = time.time()
        terminal_status_polls = 0

        while True:
            if await request.is_disconnected():
                break

            # 1 query on the hot path: fetch any new events.
            events = await asyncio.to_thread(db.get_job_events, run_id, current_seq)
            if events:
                terminal_event_seen = False
                for ev in events:
                    seq_id = ev["seq_id"]
                    ev_type = ev["event_type"]
                    payload = json.dumps(ev["payload"]) if not isinstance(ev["payload"], str) else ev["payload"]
                    yield f"id: {seq_id}\nevent: {ev_type}\ndata: {payload}\n\n"
                    current_seq = max(current_seq, seq_id)
                    if ev_type in _TERMINAL_EVENT_TYPES:
                        terminal_event_seen = True
                last_heartbeat = time.time()
                if terminal_event_seen:
                    # Terminal event delivered: safe to close the stream.
                    break
            else:
                # Idle: only now pay for a status query (single query per iteration).
                j = await asyncio.to_thread(db.get_research_job, run_id)
                if j and j.get("status") in _TERMINAL_JOB_STATUSES:
                    # Ordering guarantee makes the terminal event durable before the
                    # status flip; flush once more, then close (small grace for the
                    # cancel/worker race where a status write may precede the event).
                    more = await asyncio.to_thread(db.get_job_events, run_id, current_seq)
                    if not more and terminal_status_polls >= 2:
                        break
                    terminal_status_polls += 1
                    if more:
                        for ev in more:
                            seq_id = ev["seq_id"]
                            ev_type = ev["event_type"]
                            payload = json.dumps(ev["payload"]) if not isinstance(ev["payload"], str) else ev["payload"]
                            yield f"id: {seq_id}\nevent: {ev_type}\ndata: {payload}\n\n"
                            current_seq = max(current_seq, seq_id)
                        last_heartbeat = time.time()
                    await asyncio.sleep(0.1)
                    continue
                else:
                    terminal_status_polls = 0

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

    if job["status"] in _TERMINAL_JOB_STATUSES:
        return {"success": False, "message": f"Run already in terminal state: {job['status']}"}

    # Signal active background worker to halt immediately
    cancel_event = _CANCELLATION_EVENTS.get(run_id)
    if cancel_event:
        cancel_event.set()

    # Terminal event BEFORE the terminal status: a stream that sees the status
    # will always be able to flush the "cancelled" event before closing.
    db.append_job_event(run_id, "cancelled", {"message": "Run was cancelled by user."})
    updated = db.update_research_job(run_id, status="cancelled")
    if updated is False:
        return {"success": False, "message": "Run already in terminal state."}
    return {"success": True, "message": "Research run marked as cancelled."}
