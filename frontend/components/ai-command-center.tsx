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
    name: "Autonomous Researcher",
    role: "Literature & Market Intelligence",
    desc: "Executes targeted searches, digests technical docs, and validates citations.",
    icon: Search,
  },
  {
    id: 2,
    key: "writer",
    name: "Blog Author",
    role: "Publication Writer (Parallel)",
    desc: "Drafts comprehensive technical content formatted with clean markdown.",
    icon: PenTool,
    isParallelBranch: true,
  },
  {
    id: 3,
    key: "diagram",
    name: "Visual Architect",
    role: "Mermaid Diagram Engine (Parallel)",
    desc: "Synthesizes architectural topologies and flowcharts simultaneously.",
    icon: GitFork,
    isParallelBranch: true,
  },
  {
    id: 4,
    key: "director",
    name: "Editorial Director",
    role: "Quality Assurance & Synthesis",
    desc: "Assembles diagrams, validates claims, and refines final prose for publishing.",
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
  const [activeTab, setActiveTab] = useState<"squad" | "ledger">("squad");
  const [elapsed, setElapsed] = useState(0);

  // Active run timer
  useEffect(() => {
    if (!runId) {
      setElapsed(0);
      return;
    }
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, [runId]);

  const agentStatusMap = useMemo(() => {
    if (!runId) {
      return {
        researcher: { status: "pending", duration: null as number | null },
        writer: { status: "pending", duration: null as number | null },
        diagram: { status: "pending", duration: null as number | null },
        director: { status: "pending", duration: null as number | null },
      };
    }

    const taskDoneEvents = logs.filter((l) => l.type === "stage_complete");

    const isAgentDone = (matcher: (a: string) => boolean) => {
      return taskDoneEvents.some((e) => e.agent && matcher(e.agent.toLowerCase()));
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
    const researcherDuration = getAgentDuration((a) => a.includes("research"));

    // Writer (Parallel Agent 1)
    const writerDone = isAgentDone((a) => a.includes("writer") || a.includes("blog") || a.includes("author"));
    const writerDuration = getAgentDuration((a) => a.includes("writer") || a.includes("blog") || a.includes("author"));

    // Diagram (Parallel Agent 2)
    const diagramDone = isAgentDone((a) => a.includes("diagram") || a.includes("visual"));
    const diagramDuration = getAgentDuration((a) => a.includes("diagram") || a.includes("visual"));

    // Director
    const directorDone = isAgentDone((a) => a.includes("director") || a.includes("editor"));
    const directorDuration = getAgentDuration((a) => a.includes("director") || a.includes("editor"));

    return {
      researcher: {
        status: researcherDone ? "done" : stage === 1 ? "running" : "pending",
        duration: researcherDuration,
      },
      writer: {
        status: writerDone ? "done" : stage === 2 ? "running" : "pending",
        duration: writerDuration,
      },
      diagram: {
        status: diagramDone ? "done" : stage === 2 ? "running" : "pending",
        duration: diagramDuration,
      },
      director: {
        status: directorDone ? "done" : stage === 3 ? "running" : stage === 4 ? "done" : "pending",
        duration: directorDuration,
      },
    };
  }, [runId, logs, stage]);

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
        className="hidden lg:flex flex-col items-center gap-4 p-3 bg-surface border border-border rounded-2xl text-muted-foreground hover:text-foreground transition shadow-md w-14 shrink-0"
        title="Expand AI Command Center"
      >
        <Cpu className="w-5 h-5 text-blue-600 dark:text-blue-400" />
        <span className="text-[10px] font-mono uppercase tracking-widest [writing-mode:vertical-rl] rotate-180 text-muted-foreground font-semibold">
          AI Command Center
        </span>
        {runId && (
          <span className="flex h-2.5 w-2.5 relative">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-blue-600" />
          </span>
        )}
      </button>
    );
  }

  return (
    <aside
      className="w-full lg:w-80 shrink-0 flex flex-col gap-4 font-sans text-foreground"
      aria-label="AI Squad Command Center"
    >
      {/* 1. Header Card: Run Status & Time */}
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm backdrop-blur-md">
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-600 dark:text-blue-400">
              <Cpu className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold uppercase tracking-wider text-foreground">
                Squad Command
              </h3>
              <span className="text-[10px] text-muted-foreground block font-mono">
                {runId ? "Execution Active" : "Standby Mode"}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {runId && (
              <span className="flex items-center gap-1.5 px-2.5 py-1 bg-surface-raised border border-border rounded-lg text-xs font-mono text-blue-600 dark:text-blue-400">
                <Clock className="w-3 h-3 text-muted-foreground" />
                <span>{elapsed}s</span>
              </span>
            )}
            {onToggleCollapse && (
              <button
                type="button"
                onClick={onToggleCollapse}
                className="hidden lg:block p-1 hover:bg-surface-raised text-muted-foreground hover:text-foreground rounded-lg transition"
                title="Collapse Sidebar"
              >
                <XCircle className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Target Topic display */}
        {runId && topic && (
          <div className="mt-2 text-[11px] text-foreground truncate bg-surface-raised p-2 rounded-lg border border-border">
            <span className="text-muted-foreground font-mono mr-1">Target:</span>
            {topic}
          </div>
        )}

        {/* Real Metrics Badges */}
        <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-border">
          <div className="bg-surface-raised p-2 rounded-xl border border-border">
            <span className="text-[10px] text-muted-foreground uppercase font-mono block">Sources Audited</span>
            <span className="text-sm font-bold text-blue-600 dark:text-blue-400 font-mono">{sourcesCount}</span>
          </div>
          <div className="bg-surface-raised p-2 rounded-xl border border-border">
            <span className="text-[10px] text-muted-foreground uppercase font-mono block">Events Logged</span>
            <span className="text-sm font-bold text-foreground font-mono">{logs.length}</span>
          </div>
        </div>

        {/* Action button: Cancel / Trace */}
        {runId && (
          <div className="mt-3 flex items-center gap-2 pt-2 border-t border-border">
            {traceUrl && (
              <a
                href={traceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-sky-50 dark:bg-sky-950/50 hover:bg-sky-100 border border-sky-300 dark:border-sky-800 text-sky-700 dark:text-sky-300 rounded-xl text-xs font-medium transition"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>LangSmith Trace</span>
              </a>
            )}
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-400 rounded-xl text-xs font-medium transition cursor-pointer"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Cancel Execution</span>
              </button>
            )}
          </div>
        )}
      </div>

      {/* 2. Agent Squad Status Graph */}
      <div className="bg-surface border border-border rounded-2xl p-4 shadow-sm backdrop-blur-md flex-1 flex flex-col">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-border">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("squad")}
              className={`text-xs font-semibold px-2 py-1 rounded-md transition cursor-pointer ${
                activeTab === "squad"
                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              Agent Topology
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("ledger")}
              className={`text-xs font-semibold px-2 py-1 rounded-md transition flex items-center gap-1 cursor-pointer ${
                activeTab === "ledger"
                  ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Terminal className="w-3 h-3" />
              <span>Activity Ledger</span>
            </button>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground">
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
                      ? "bg-blue-50/60 dark:bg-blue-950/40 border-blue-500/60 shadow-sm ring-1 ring-blue-500/30"
                      : isDone
                      ? "bg-surface-raised border-border text-foreground"
                      : "bg-surface border-border/60 text-muted-foreground opacity-60"
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <div
                        className={`p-1.5 rounded-lg ${
                          isRunning
                            ? "bg-blue-600 text-white"
                            : isDone
                            ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30"
                            : "bg-surface-raised text-muted-foreground border border-border"
                        }`}
                      >
                        <Icon className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                          {agent.name}
                          {agent.isParallelBranch && (
                            <span className="text-[9px] px-1 py-0.2 bg-surface-raised text-muted-foreground rounded border border-border">
                              Parallel
                            </span>
                          )}
                        </h4>
                        <span className="text-[10px] text-muted-foreground block font-mono">{agent.role}</span>
                      </div>
                    </div>

                    {/* Status Indicator */}
                    <div className="flex items-center gap-1">
                      {isRunning && (
                        <span className="flex items-center gap-1 text-[10px] font-mono text-blue-600 dark:text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded-full border border-blue-500/30">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span>Active</span>
                        </span>
                      )}
                      {isDone && (
                        <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                          <CheckCircle className="w-3 h-3" />
                          <span>Done {durationSec ? `(${durationSec}s)` : ""}</span>
                        </span>
                      )}
                      {isPending && (
                        <span className="text-[10px] font-mono text-muted-foreground">Pending</span>
                      )}
                    </div>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-1 mt-1">{agent.desc}</p>
                </div>
              );
            })}
          </div>
        ) : (
          /* Live Agent Activity Ledger */
          <div className="flex-1 flex flex-col font-mono text-xs">
            <div className="text-[10px] text-muted-foreground mb-2 flex items-center justify-between">
              <span>Sequenced Backend Stream</span>
              <span>{logs.length} entries</span>
            </div>
            <div
              role="log"
              aria-label="Agent execution logs"
              className="flex-1 max-h-72 overflow-y-auto space-y-2 pr-1"
            >
              {logs.map((log, idx) => (
                <div key={idx} className="p-2 bg-surface-raised border border-border rounded-lg text-foreground">
                  <div className="flex items-center justify-between text-[10px] mb-1">
                    <span className="text-blue-600 dark:text-blue-400 font-bold uppercase">[{log.type}]</span>
                    {log.agent && (
                      <span className="text-cyan-600 dark:text-cyan-400 font-mono font-semibold">[{log.agent}]</span>
                    )}
                    {log.timestamp && (
                      <span className="text-muted-foreground">
                        {new Date(log.timestamp * 1000).toLocaleTimeString([], { hour12: false })}
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-foreground break-words leading-relaxed">
                    {log.detail || JSON.stringify(log)}
                  </p>
                </div>
              ))}
              {logs.length === 0 && (
                <div className="text-center p-6 text-xs text-muted-foreground italic">
                  No execution activity logged yet.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Warnings or Errors Display */}
        {errorsOrWarnings.length > 0 && (
          <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-700 dark:text-amber-400 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block">Execution Warning</span>
              <span className="text-[11px] text-amber-800 dark:text-amber-300/80">
                {errorsOrWarnings[errorsOrWarnings.length - 1].detail || "Warning noted during pipeline run."}
              </span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
