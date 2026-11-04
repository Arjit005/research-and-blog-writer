"""UI Stepper Component & State Reducer for the 4-Agent Pipeline.

Renders a live 4-stage visual stepper (Researcher -> Analyst -> Author -> Reviewer).
Includes pure event reduction, duration calculations, and accessible HTML/CSS
with prefers-reduced-motion support.
"""

from __future__ import annotations

import time
import html
from typing import Dict, Any, List, Optional

STAGES = [
    {
        "id": 1,
        "name": "Senior Researcher",
        "icon": "🔍",
        "default_detail": "Live web search & paper scraping",
    },
    {
        "id": 2,
        "name": "Systems Analyst",
        "icon": "📊",
        "default_detail": "Designing Mermaid diagrams & matrices",
    },
    {
        "id": 3,
        "name": "Lead Author",
        "icon": "✍️",
        "default_detail": "Drafting deep-dive technical narrative",
    },
    {
        "id": 4,
        "name": "Quality Reviewer",
        "icon": "✨",
        "default_detail": "Auditing facts, diagram syntax & citations",
    },
]


def init_stepper_state() -> Dict[str, Any]:
    """Initialize default pending state for all 4 stages."""
    state = {
        "active_stage": 0,
        "is_finished": False,
        "has_error": False,
        "error_message": "",
        "stages": {},
    }
    for s in STAGES:
        state["stages"][s["id"]] = {
            "status": "pending",  # 'pending', 'running', 'done', 'error'
            "detail": s["default_detail"],
            "duration_sec": None,
            "start_time": None,
        }
    return state


def reduce_stepper_event(state: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """Pure state reducer for pipeline events.

    Events:
    - {'type': 'run_start', 'timestamp': float}
    - {'type': 'step', 'stage_id': int, 'detail': str}
    - {'type': 'task_done', 'stage_id': int, 'output_preview': str, 'timestamp': float}
    - {'type': 'error', 'stage_id': int, 'message': str}
    - {'type': 'run_done', 'timestamp': float}
    """
    new_state = {
        "active_stage": state.get("active_stage", 0),
        "is_finished": state.get("is_finished", False),
        "has_error": state.get("has_error", False),
        "error_message": state.get("error_message", ""),
        "stages": {k: dict(v) for k, v in state.get("stages", {}).items()},
    }

    event_type = event.get("type")
    now = event.get("timestamp", time.time())

    if event_type == "run_start":
        new_state["active_stage"] = 1
        new_state["is_finished"] = False
        new_state["has_error"] = False
        new_state["error_message"] = ""
        # Mark stage 1 running
        if 1 in new_state["stages"]:
            new_state["stages"][1]["status"] = "running"
            new_state["stages"][1]["start_time"] = now

    elif event_type == "step":
        active_id = event.get("stage_id") or new_state["active_stage"]
        detail = event.get("detail", "")
        if active_id in new_state["stages"] and detail:
            new_state["stages"][active_id]["detail"] = detail[:120]

    elif event_type == "task_done":
        stage_id = event.get("stage_id", new_state["active_stage"])
        if stage_id in new_state["stages"]:
            st_info = new_state["stages"][stage_id]
            st_info["status"] = "done"
            if st_info.get("start_time"):
                st_info["duration_sec"] = round(now - st_info["start_time"], 1)

        # Advance to next stage if available
        next_stage_id = stage_id + 1
        if next_stage_id in new_state["stages"]:
            new_state["active_stage"] = next_stage_id
            new_state["stages"][next_stage_id]["status"] = "running"
            new_state["stages"][next_stage_id]["start_time"] = now
        else:
            new_state["active_stage"] = 4
            new_state["is_finished"] = True

    elif event_type == "error":
        stage_id = event.get("stage_id", new_state["active_stage"]) or 1
        new_state["has_error"] = True
        new_state["error_message"] = event.get("message", "An unexpected error occurred.")
        if stage_id in new_state["stages"]:
            new_state["stages"][stage_id]["status"] = "error"
            new_state["stages"][stage_id]["detail"] = new_state["error_message"][:120]

    elif event_type == "run_done":
        new_state["is_finished"] = True
        # Mark all non-errored stages done if completed
        for s_id, s_val in new_state["stages"].items():
            if s_val["status"] == "running":
                s_val["status"] = "done"
                if s_val.get("start_time"):
                    s_val["duration_sec"] = round(now - s_val["start_time"], 1)

    return new_state


def render_stepper_html(state: Dict[str, Any]) -> str:
    """Generate accessible, responsive HTML for the 4-stage stepper with prefers-reduced-motion."""
    stages_data = state.get("stages", {})

    cards_html = []
    for s_meta in STAGES:
        s_id = s_meta["id"]
        s_info = stages_data.get(s_id, {"status": "pending", "detail": s_meta["default_detail"]})
        status = s_info.get("status", "pending")
        detail = html.escape(s_info.get("detail", s_meta["default_detail"]))
        duration = s_info.get("duration_sec")

        if status == "running":
            badge_icon = "⏳"
            badge_label = "Running"
            card_class = "stage-card stage-running"
            status_pill = f'<span class="status-pill pill-running">Active</span>'
        elif status == "done":
            badge_icon = "✅"
            dur_text = f"{duration}s" if duration is not None else "Done"
            badge_label = dur_text
            card_class = "stage-card stage-done"
            status_pill = f'<span class="status-pill pill-done">{dur_text}</span>'
        elif status == "error":
            badge_icon = "❌"
            badge_label = "Failed"
            card_class = "stage-card stage-error"
            status_pill = f'<span class="status-pill pill-error">Error</span>'
        else:
            badge_icon = "○"
            badge_label = "Pending"
            card_class = "stage-card stage-pending"
            status_pill = f'<span class="status-pill pill-pending">Pending</span>'

        cards_html.append(f"""
        <div class="{card_class}">
          <div class="card-header">
            <span class="agent-icon">{s_meta['icon']}</span>
            <div class="agent-title-block">
              <span class="stage-num">Step {s_id}</span>
              <span class="agent-name">{s_meta['name']}</span>
            </div>
            {status_pill}
          </div>
          <div class="card-detail">{detail}</div>
        </div>
        """)

    cards_joined = "\n".join(cards_html)

    return f"""
    <style>
      .stepper-container {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 12px;
        margin: 16px 0 20px 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      }}
      @media (max-width: 900px) {{
        .stepper-container {{
          grid-template-columns: repeat(2, 1fr);
        }}
      }}
      @media (max-width: 550px) {{
        .stepper-container {{
          grid-template-columns: 1fr;
        }}
      }}
      .stage-card {{
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 14px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 96px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        transition: border-color 0.2s ease, box-shadow 0.2s ease;
      }}
      .stage-pending {{
        border-color: #e2e8f0;
        background: #f8fafc;
        opacity: 0.85;
      }}
      .stage-running {{
        border-color: #4f46e5;
        background: #ffffff;
        box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.15), 0 4px 12px rgba(79, 70, 229, 0.08);
      }}
      @media (prefers-reduced-motion: no-preference) {{
        .stage-running {{
          animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
        }}
      }}
      @keyframes pulse-ring {{
        0%, 100% {{ border-color: #4f46e5; }}
        50% {{ border-color: #818cf8; }}
      }}
      .stage-done {{
        border-color: #10b981;
        background: #ffffff;
      }}
      .stage-error {{
        border-color: #ef4444;
        background: #fef2f2;
      }}
      .card-header {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 6px;
      }}
      .agent-icon {{
        font-size: 18px;
      }}
      .agent-title-block {{
        display: flex;
        flex-direction: column;
        flex: 1;
      }}
      .stage-num {{
        font-size: 10px;
        text-transform: uppercase;
        color: #64748b;
        font-weight: 700;
        letter-spacing: 0.5px;
      }}
      .agent-name {{
        font-size: 13px;
        font-weight: 700;
        color: #0f172a;
      }}
      .status-pill {{
        font-size: 10px;
        font-weight: 700;
        padding: 2px 7px;
        border-radius: 9999px;
      }}
      .pill-pending {{
        background: #e2e8f0;
        color: #475569;
      }}
      .pill-running {{
        background: #e0e7ff;
        color: #4338ca;
      }}
      .pill-done {{
        background: #d1fae5;
        color: #065f46;
      }}
      .pill-error {{
        background: #fee2e2;
        color: #991b1b;
      }}
      .card-detail {{
        font-size: 11px;
        color: #475569;
        line-height: 1.35;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
    </style>
    <div class="stepper-container">
      {cards_joined}
    </div>
    """
