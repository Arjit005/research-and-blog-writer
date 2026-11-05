"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  Search,
  PenTool,
  GitFork,
  CheckCircle,
  Loader2,
  XCircle,
  Clock,
  ExternalLink,
  Terminal,
  AlertTriangle,
  Cpu,
} from "lucide-react";

export interface SquadLog {
  type: string;
  detail?: string;
  agent?: string;
  timestamp?: number;
  parallel?: boolean;
}

interface CommandCenterProps {
  runId: string | null;
  topic: string;
  stage: number;
  logs: SquadLog[];
  onCancel?: () => void;
  traceUrl?: string | null;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  articleSummary?: {
    wordCount?: number;
    sourcesCount?: number;
    generationTime?: number;
  };
}

interface AgentState {
  id: number;
  key: string;
  name: string;
  role: string;
  desc: string;
  icon: typeof Search;
  isParallelBranch?: boolean;
}

const SQUAD_AGENTS: AgentState[] = [
  {
    id: 1,
    key: "researcher",
    name: "Lead Researcher",
    role: "Senior Research Analyst",
    desc: "Exhaustive web crawl, technical citations & benchmark verification",
    icon: Search,
  },
  {
    id: 2,
    key: "writer",
    name: "Technical Writer",
    role: "Deep-Tech Author",
    desc: "Synthesizing architectural narrative & systems analysis",
    icon: PenTool,
    isParallelBranch: true,
  },
  {
    id: 3,
    key: "diagram",
    name: "Diagram Architect",
    role: "Mermaid.js Synthesizer",
    desc: "Compiling system dataflow & topology visual specifications",
    icon: GitFork,
    isParallelBranch: true,
  },
  {
    id: 4,
    key: "director",
    name: "Editorial Director",
    role: "Executive Reviewer",
    desc: "Rigorous quality audit, citation validation & final polish",
    icon: CheckCircle,
  },
];

export function AICommandCenter({
  runId,
  topic,
  stage,
  logs,
  onCancel,
  traceUrl,
  isCollapsed = false,
  onToggleCollapse,
  articleSummary,
}: CommandCenterProps) {
  const [elapsed, setElapsed] = useState(0);
  const [activeTab, setActiveTab] = useState<"squad" | "ledger">("squad");

  // Track run duration timer; reset when runId is null or changes
  useEffect(() => {
    if (!runId) {
      setElapsed(0);
      return;
    }
    setElapsed(0);
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [runId]);

  // Derive individual agent status and duration from actual logs & events
  // Finding 1: Track Writer & Diagram Architect independently from real agent events
  // Finding 3: Durations and status reset whenever runId is null/changes
  const agentStatusMap = useMemo(() => {
    if (!runId) {
      return {
        researcher: { status: "pending", duration: null as number | null },
        writer: { status: "pending", duration: null as number | null },
        diagram: { status: "pending", duration: null as number | null },
        director: { status: "pending", duration: null as number | null },
      };
    }

    // Check completed task events from logs
    const taskDoneEvents = logs.filter((l) => l.type === "stage_complete");
    const stepEvents = logs.filter((l) => l.type === "step");

    // Helper to check if an agent has completed or started
    const isAgentDone = (matcher: (a: string) => boolean) => {
      return taskDoneEvents.some((e) => e.agent && matcher(e.agent.toLowerCase()));
    };

    const _isAgentActive = (matcher: (a: string) => boolean) => {
      return stepEvents.some((e) => e.agent && matcher(e.agent.toLowerCase()));
    };

    const getAgentDuration = (matcher: (a: string) => boolean) => {
      const match = taskDoneEvents.find((e) => e.agent && matcher(e.agent.toLowerCase()));
      if (match && match.detail) {
        const m = match.detail.match(/\(([\d.]+)s\)/);
        if (m) return parseFloat(m[1]);
      }
      return null;
    };

    // Researcher
    const researcherDone = isAgentDone((a) => a.includes("research"));
    const researcherRunning = !researcherDone && stage === 1;
    const researcherDuration = getAgentDuration((a) => a.includes("research"));

    // Writer (Parallel Agent 1)
    const writerDone = isAgentDone((a) => a.includes("writer") || a.includes("blog") || a.includes("author"));
    const writerDuration = getAgentDuration((a) => a.includes("writer") || a.includes("blog") || a.includes("author"));
    // Starts when researcher is done
    const writerRunning = !writerDone && (researcherDone || stage >= 2) && stage < 4;

    // Diagram Architect (Parallel Agent 2)
    const diagramDone = isAgentDone((a) => a.includes("analyst") || a.includes("diagram") || a.includes("content"));
    const diagramDuration = getAgentDuration((a) => a.includes("analyst") || a.includes("diagram") || a.includes("content"));
    // Starts when researcher is done
    const diagramRunning = !diagramDone && (researcherDone || stage >= 2) && stage < 4;

    // Editorial Director (Starts ONLY after BOTH parallel agents succeed)
    const bothParallelDone = (writerDone && diagramDone) || stage >= 4;
    const directorDone = isAgentDone((a) => a.includes("reviewer") || a.includes("editor") || a.includes("quality"));
    const directorDuration = getAgentDuration((a) => a.includes("reviewer") || a.includes("editor") || a.includes("quality"));
    const directorRunning = bothParallelDone && !directorDone && stage >= 4;

    return {
      researcher: {
        status: researcherDone ? "done" : researcherRunning ? "running" : "pending",
        duration: researcherDuration,
      },
      writer: {
        status: writerDone ? "done" : writerRunning ? "running" : "pending",
        duration: writerDuration,
      },
      diagram: {
        status: diagramDone ? "done" : diagramRunning ? "running" : "pending",
        duration: diagramDuration,
      },
      director: {
        status: directorDone ? "done" : directorRunning ? "running" : "pending",
        duration: directorDuration,
      },
    };
  }, [runId, stage, logs]);

  // Derived metrics from logs
  const citationMatches = logs.filter(
    (l) =>
      l.detail?.toLowerCase().includes("http") ||
      l.detail?.toLowerCase().includes("source") ||
      l.detail?.toLowerCase().includes("citation")
  ).length;

  const errorsOrWarnings = logs.filter(
    (l) =>
      l.type === "error" ||
      l.type === "warning" ||
      l.detail?.toLowerCase().includes("retry") ||
      l.detail?.toLowerCase().includes("warn")
  );

  const sourcesCount = articleSummary?.sourcesCount ?? citationMatches;

  if (isCollapsed) {
    return (
      <button
        type="button"
        onClick={onToggleCollapse}
        className="hidden lg:flex flex-col items-center gap-4 p-3 bg-slate-900/80 hover:bg-slate-900 border border-slate-800 rounded-2xl text-slate-400 hover:text-slate-200 transition shadow-xl w-14 shrink-0"
        title="Expand AI Command Center"
      >
        <Cpu className="w-5 h-5 text-indigo-400" />
        <span className="text-[10px] font-mono uppercase tracking-widest [writing-mode:vertical-rl] rotate-180 text-slate-400 font-semibold">
          AI Command Center
        </span>
        {runId && (
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-indigo-500" />
          </span>
        )}
      </button>
    );
  }

  return (
    <aside
      className="w-full lg:w-80 shrink-0 flex flex-col gap-4 font-sans"
      aria-label="AI Squad Command Center"
    >
      {/* 1. Header Card: Run Status & Time */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800/70">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-indigo-600/10 border border-indigo-500/20 text-indigo-400">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                Squad Command
              </h3>
              <span className="text-[10px] text-slate-400 block font-mono">
                {runId ? "Execution Active" : "Standby Mode"}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {runId && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-950/80 border border-slate-800 rounded-lg text-xs font-mono text-indigo-300">
                <Clock className="w-3 h-3 text-slate-400" />
                <span>{elapsed}s</span>
              </span>
            )}
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="hidden lg:block p-1 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
                title="Collapse Sidebar"
              >
                <XCircle className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Target Topic display */}
        {runId && topic && (
          <div className="mt-2 text-[11px] text-slate-400 truncate bg-slate-950/60 p-2 rounded-lg border border-slate-800/60">
            <span className="text-slate-500 font-mono mr-1">Target:</span>
            {topic}
          </div>
        )}

        {/* Real Metrics Badges */}
        <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-slate-800/60">
          <div className="bg-slate-950/80 p-2 rounded-xl border border-slate-800/70">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">Sources Audited</span>
            <span className="text-sm font-bold text-indigo-300 font-mono">{sourcesCount}</span>
          </div>
          <div className="bg-slate-950/80 p-2 rounded-xl border border-slate-800/70">
            <span className="text-[10px] text-slate-500 uppercase font-mono block">Events Logged</span>
            <span className="text-sm font-bold text-slate-200 font-mono">{logs.length}</span>
          </div>
        </div>

        {/* Action button: Cancel / Trace */}
        {runId && (
          <div className="mt-3 flex items-center gap-2 pt-2 border-t border-slate-800/60">
            {traceUrl && (
              <a
                href={traceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-cyan-950/50 hover:bg-cyan-900/60 border border-cyan-800/80 text-cyan-300 rounded-xl text-xs font-medium transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>LangSmith Trace</span>
              </a>
            )}
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 rounded-xl text-xs font-medium transition"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Cancel Execution</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* 2. Agent Squad Status Graph */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 shadow-xl backdrop-blur-md flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/70">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("squad")}
              className={`text-xs font-semibold px-2 py-1 rounded-md transition cursor-pointer ${
                activeTab === "squad"
                  ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Agent Topology
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("ledger")}
              className={`text-xs font-semibold px-2 py-1 rounded-md transition flex items-center gap-1 cursor-pointer ${
                activeTab === "ledger"
                  ? "bg-indigo-600/20 text-indigo-400 border border-indigo-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Terminal className="w-3 h-3" />
              <span>Activity Ledger</span>
            </button>
          </div>
          <span className="text-[10px] font-mono text-slate-500">
            {runId ? `Stage ${stage}/4` : "Idle"}
          </span>
        </div>

        {activeTab === "squad" ? (
          <div className="space-y-3 flex-1">
            {SQUAD_AGENTS.map((agent) => {
              const Icon = agent.icon;
              const agentState = agentStatusMap[agent.key as keyof typeof agentStatusMap] || {
                status: "pending",
                duration: null,
              };
              const isRunning = agentState.status === "running";
              const isDone = agentState.status === "done";
              const isPending = agentState.status === "pending";
              const durationSec = agentState.duration;

              return (
                <div
                  key={agent.id}
                  className={`relative p-3 rounded-xl border transition-all ${
                    isRunning
                      ? "bg-indigo-950/40 border-indigo-500/60 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30"
                      : isDone
                      ? "bg-slate-900/60 border-slate-800/90 text-slate-300"
                      : "bg-slate-950/40 border-slate-800/50 text-slate-500 opacity-60"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <div
                        className={`p-1.5 rounded-lg ${
                          isRunning
                            ? "bg-indigo-600 text-white"
                            : isDone
                            ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                            : "bg-slate-800 text-slate-500"
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <h4 className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                          {agent.name}
                          {agent.isParallelBranch && (
                            <span className="text-[9px] px-1 py-0.2 bg-slate-800 text-slate-400 rounded border border-slate-700/50">
                              Parallel
                            </span>
                          )}
                        </h4>
                        <span className="text-[10px] text-slate-400 block font-mono">{agent.role}</span>
                      </div>
                    </div>

                    {/* Status Indicator */}
                    <div className="flex items-center gap-1">
                      {isRunning && (
                        <span className="flex items-center gap-1 text-[10px] font-mono text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/30">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>Active</span>
                        </span>
                      )}
                      {isDone && (
                        <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                          <CheckCircle className="w-3 h-3" />
                          <span>Done {durationSec ? `(${durationSec}s)` : ""}</span>
                        </span>
                      )}
                      {isPending && (
                        <span className="text-[10px] font-mono text-slate-500">Pending</span>
                      )}
                    </div>
                  </div>
                  <p className="text-[11px] text-slate-400 line-clamp-1 mt-1">{agent.desc}</p>
                </div>
              );
            })}
          </div>
        ) : (
          /* Live Agent Activity Ledger */
          <div className="flex-1 flex flex-col font-mono text-xs">
            <div className="text-[10px] text-slate-500 mb-2 flex items-center justify-between">
              <span>Sequenced Backend Stream</span>
              <span>{logs.length} entries</span>
            </div>
            <div
              role="log"
              aria-label="Agent execution logs"
              className="flex-1 max-h-72 overflow-y-auto space-y-2 pr-1"
            >
              {logs.map((log, idx) => (
                <div key={idx} className="p-2 bg-slate-950/70 border border-slate-800/80 rounded-lg text-slate-300">
                  <div className="flex items-center justify-between text-[10px] mb-1">
                    <span className="text-indigo-400 font-bold uppercase">[{log.type}]</span>
                    {log.agent && (
                      <span className="text-cyan-400 font-mono font-semibold">[{log.agent}]</span>
                    )}
                    {log.timestamp && (
                      <span className="text-slate-500">
                        {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour12: false })}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-300 break-words leading-relaxed">
                    {log.detail || JSON.stringify(log)}
                  </p>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="text-center p-6 text-xs text-slate-500 italic">
                  No execution activity logged yet.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Warnings or Errors Display */}
        {errorsOrWarnings.length > 0 && (
          <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block">Execution Warning</span>
              <span className="text-[11px] text-amber-300/80">
                {errorsOrWarnings[errorsOrWarnings.length - 1].detail || "Warning noted during pipeline run."}
              </span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
