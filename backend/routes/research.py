"""Research Runs API endpoints (Job Model, Background Execution & Resumable SSE Stream)."""

from __future__ import annotations

import os
import json
import time
import uuid
import asyncio
import logging
import threading
from typing import Dict, Any, Optional, Set

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

# Active in-memory token broadcasting channels for live token-by-token streaming.
# Mapping: run_id -> set of asyncio.Queue instances (one queue per active SSE client).
_RUN_TOKEN_LISTENERS: Dict[str, Set[asyncio.Queue]] = {}
_RUN_TOKEN_LOCK = threading.Lock()


def register_token_listener(run_id: str, q: asyncio.Queue) -> None:
    with _RUN_TOKEN_LOCK:
        if run_id not in _RUN_TOKEN_LISTENERS:
            _RUN_TOKEN_LISTENERS[run_id] = set()
        _RUN_TOKEN_LISTENERS[run_id].add(q)


def unregister_token_listener(run_id: str, q: asyncio.Queue) -> None:
    with _RUN_TOKEN_LOCK:
        listeners = _RUN_TOKEN_LISTENERS.get(run_id)
        if listeners:
            listeners.discard(q)
            if not listeners:
                _RUN_TOKEN_LISTENERS.pop(run_id, None)


def broadcast_run_token(run_id: str, chunk: str) -> None:
    """Thread-safe non-blocking broadcast of a token chunk to all active SSE listeners."""
    with _RUN_TOKEN_LOCK:
        listeners = list(_RUN_TOKEN_LISTENERS.get(run_id, []))
    for q in listeners:
        try:
            q.put_nowait(chunk)
        except Exception:
            # Drop chunk if consumer queue is overflowing or closed
            pass


def cleanup_run_tokens(run_id: str) -> None:
    with _RUN_TOKEN_LOCK:
        _RUN_TOKEN_LISTENERS.pop(run_id, None)

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

        stage_lock = threading.Lock()
        completed_tasks_count = 0
        stage_start_times: Dict[str, float] = {"stage_1": time.time()}

        def on_step(step_output: Any) -> None:
            _raise_if_cancelled()
            detail = ""
            agent_role = ""
            if hasattr(step_output, "agent"):
                agent_role = str(getattr(step_output.agent, "role", ""))
            elif hasattr(step_output, "agent_role"):
                agent_role = str(getattr(step_output, "agent_role", ""))

            if hasattr(step_output, "tool"):
                tool_name = getattr(step_output, "tool", "Tool")
                tool_input = str(getattr(step_output, "tool_input", ""))[:60]
                detail = f"Running {tool_name} ({tool_input})"
            elif hasattr(step_output, "text") and step_output.text:
                detail = str(step_output.text).strip()[:80]
            elif isinstance(step_output, str):
                detail = step_output.strip()[:80]

            if detail:
                safe_detail = mask_pii_and_secrets(detail)[:120]
                now_ts = time.time()
                payload = {
                    "detail": safe_detail,
                    "agent": agent_role or "Agent",
                    "timestamp": now_ts,
                }
                db.append_job_event(run_id, "step", payload)

        def on_task(task_output: Any) -> None:
            _raise_if_cancelled()
            nonlocal completed_tasks_count
            now_ts = time.time()

            # Identify which task finished
            task_agent_role = ""
            if hasattr(task_output, "agent"):
                task_agent_role = str(getattr(task_output.agent, "role", str(task_output.agent)))

            with stage_lock:
                completed_tasks_count += 1
                completed_now = completed_tasks_count

                if completed_now == 1:
                    # Stage 1 (Lead Researcher) completed.
                    s1_start = stage_start_times.get("stage_1", now_ts)
                    s1_dur = round(now_ts - s1_start, 2)
                    tracer.end_span("stage_0")
                    # Parallel Stage 2 begins for both Diagram Architect and Technical Writer
                    stage_start_times["stage_2_parallel"] = now_ts
                    tracer.start_span("stage_1_parallel", "CrewAI Parallel Stage: Writer & Diagram Architect", run_type="chain")
                    db.append_job_event(run_id, "task_done", {
                        "completed_stage": 1,
                        "agent": task_agent_role or "Senior Researcher",
                        "duration_sec": s1_dur,
                        "timestamp": now_ts,
                        "parallel": False,
                        "message": "Lead Research complete. Parallel generation underway.",
                    })

                elif completed_now == 2:
                    # First of the two parallel agents finished
                    p_start = stage_start_times.get("stage_2_parallel", now_ts)
                    p_dur = round(now_ts - p_start, 2)
                    db.append_job_event(run_id, "task_done", {
                        "completed_stage": 2,
                        "agent": task_agent_role or "Parallel Agent",
                        "duration_sec": p_dur,
                        "timestamp": now_ts,
                        "parallel": True,
                        "message": f"Parallel agent finished ({task_agent_role or 'Stage 2 agent'}). Awaiting partner agent.",
                    })

                elif completed_now == 3:
                    # Both parallel Stage 2 agents have finished. Stage 3 (Editorial Director) begins.
                    p_start = stage_start_times.get("stage_2_parallel", now_ts)
                    p_dur = round(now_ts - p_start, 2)
                    tracer.end_span("stage_1_parallel")
                    stage_start_times["stage_3_review"] = now_ts
                    tracer.start_span("stage_2_review", "CrewAI Stage: Editorial Review & Synthesis", run_type="chain")
                    db.append_job_event(run_id, "task_done", {
                        "completed_stage": 3,
                        "agent": task_agent_role or "Parallel Agent",
                        "duration_sec": p_dur,
                        "timestamp": now_ts,
                        "parallel": True,
                        "message": "Parallel Stage complete. Both technical narrative and diagrams ready for Editorial Review.",
                    })

                elif completed_now >= 4:
                    # Stage 3 (Quality Reviewer / Editorial Director) finished
                    r_start = stage_start_times.get("stage_3_review", now_ts)
                    r_dur = round(now_ts - r_start, 2)
                    tracer.end_span("stage_2_review")
                    db.append_job_event(run_id, "task_done", {
                        "completed_stage": 4,
                        "agent": task_agent_role or "Quality Reviewer",
                        "duration_sec": r_dur,
                        "timestamp": now_ts,
                        "parallel": False,
                        "message": "Editorial Director completed final quality review and audit.",
                    })

        # Resolve API keys: user-specific credentials take precedence over environment
        user_keys = db.get_user_api_keys(user_id=user_id) if (user_id and hasattr(db, "get_user_api_keys")) else {}
        u_gemini = user_keys.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
        u_beatapi = user_keys.get("beatapi_key") or os.getenv("BEATAPI_KEY") or os.getenv("BEAT_API_KEY")
        u_openrouter = user_keys.get("openrouter_api_key") or os.getenv("OPENROUTER_API_KEY")

        from llm_fallback import scoped_llm_keys
        
        # Subscribe to crewai stream chunk events for Blog Writer to stream drafts in real time
        from crewai.events.event_bus import crewai_event_bus
        from crewai.events.types.llm_events import LLMStreamChunkEvent

        def _on_llm_chunk(source: Any, event: Any) -> None:
            if _job_is_cancelled(run_id, cancel_event):
                return
            chunk_str = str(getattr(event, "chunk", "") or "")
            if not chunk_str:
                return
            agent_role = str(getattr(event, "agent_role", "") or "").lower()
            if not agent_role:
                from_agent = getattr(event, "from_agent", None)
                agent_role = str(getattr(from_agent, "role", "") or "").lower()
            # Stream Writer or any drafting agent tokens to live UI
            if not agent_role or any(w in agent_role for w in ("writer", "author", "blog", "draft")):
                broadcast_run_token(run_id, chunk_str)

        crewai_event_bus.register_handler(LLMStreamChunkEvent, _on_llm_chunk)

        try:
            with scoped_llm_keys(openrouter_key=u_openrouter, gemini_key=u_gemini, beatapi_key=u_beatapi):
                start_time = time.time()
                _reset_llm_usage_stats()
                crew_instance = ResearchAndBlogWriter()
                crew_obj = crew_instance.crew(step_callback=on_step, task_callback=on_task)
                result = crew_obj.kickoff(inputs={"topic": safe_topic})
                usage_stats = _get_llm_usage_stats()
        finally:
            try:
                crewai_event_bus.off(LLMStreamChunkEvent, _on_llm_chunk)
            except Exception:
                pass

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
        cleanup_run_tokens(run_id)


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
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)
    register_token_listener(run_id, token_queue)

    async def event_generator():
        current_seq = start_seq
        last_heartbeat = time.time()
        terminal_status_polls = 0

        try:
            while True:
                if await request.is_disconnected():
                    break

                # 1. Drain any pending live tokens immediately with zero DB delay
                token_emitted = False
                while not token_queue.empty():
                    try:
                        chunk = token_queue.get_nowait()
                        token_payload = json.dumps({"delta": chunk})
                        yield f"event: token\ndata: {token_payload}\n\n"
                        token_emitted = True
                        last_heartbeat = time.time()
                    except asyncio.QueueEmpty:
                        break

                # 2. Check for sequenced durable job events in DB
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
                        await asyncio.sleep(0.05)
                        continue
                    else:
                        terminal_status_polls = 0

                # Heartbeat to keep connection alive
                if time.time() - last_heartbeat >= 15:
                    yield ": ping\n\n"
                    last_heartbeat = time.time()

                # If tokens are rapidly arriving, check queue immediately; otherwise yield to event loop briefly
                if token_emitted:
                    await asyncio.sleep(0.02)
                else:
                    await asyncio.sleep(0.2)
        finally:
            unregister_token_listener(run_id, token_queue)

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
