"use client";

import React, { useEffect, useState } from "react";
import { Search, PenTool, GitFork, CheckCircle, Loader2, XCircle, Clock, ExternalLink, Zap } from "lucide-react";

interface LogEntry {
  type: string;
  detail?: string;
  agent?: string;
  timestamp?: number;
  parallel?: boolean;
}

interface LiveStepperProps {
  runId: string;
  topic: string;
  onCancel?: () => void;
  logs: LogEntry[];
  stage: number;
  traceUrl?: string | null;
}

export function LiveStepper({ topic, onCancel, logs, stage, traceUrl }: LiveStepperProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Stage mapping:
  // stage === 1: Stage 1 (Lead Researcher) is running
  // stage === 2: Stage 2 (Technical Writer & Diagram Architect) are running in parallel
  // stage === 3: Stage 2 second agent completing / transitioning to Stage 3
  // stage >= 4: Stage 3 (Editorial Director) is running / completed

  const stage1Done = stage > 1;
  const stage1Current = stage === 1;

  const stage2Done = stage >= 4;
  const stage2Running = stage === 2 || stage === 3;

  const stage3Done = stage > 4;
  const stage3Current = stage === 4;

  return (
    <div className="w-full bg-surface/90 border border-border rounded-2xl p-6 shadow-xl backdrop-blur-md">
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-border gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-signal uppercase tracking-wider mb-1">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-signal opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-signal"></span>
            </span>
            Active Hybrid Parallel Research Run
          </div>
          <h3 className="text-lg font-bold text-foreground line-clamp-1">{topic}</h3>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised/80 rounded-lg text-xs font-mono text-foreground">
            <Clock className="w-3.5 h-3.5 text-muted-foreground" aria-hidden="true" />
            <span>{elapsed}s elapsed</span>
          </div>

          {traceUrl && (
            <a
              href={traceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-surface/70 hover:bg-surface text-signal border border-signal rounded-lg text-xs font-medium transition"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>LangSmith Trace</span>
            </a>
          )}

          {onCancel && (
            <button
              onClick={onCancel}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg text-xs font-medium transition"
            >
              <XCircle className="w-3.5 h-3.5" />
              Cancel Run
            </button>
          )}
        </div>
      </div>

      {/* 3-Stage Hybrid Parallel Stepper Track */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 my-6">
        {/* Stage 1: Lead Researcher */}
        <div
          aria-current={stage1Current ? "step" : undefined}
          className={`p-4 rounded-xl border transition-all ${
            stage1Current
              ? "bg-accent/40 border-signal/50 shadow-lg shadow-indigo-500/10 ring-1 ring-signal/30"
              : stage1Done
              ? "bg-surface-raised/30 border-border/60 text-muted-foreground"
              : "bg-surface/40 border-border/50 text-muted-foreground opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div
              className={`p-2 rounded-lg ${
                stage1Current
                  ? "bg-accent text-white"
                  : stage1Done
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-surface-raised text-muted-foreground"
              }`}
            >
              <Search className="w-4 h-4" />
            </div>
            {stage1Current && <Loader2 className="w-4 h-4 text-signal animate-spin" />}
            {stage1Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-foreground">STAGE 1</span>
          </div>
          <h4 className={`text-sm font-semibold mb-0.5 mt-1 ${stage1Current ? "text-foreground" : ""}`}>
            Lead Researcher
          </h4>
          <p className="text-xs text-muted-foreground line-clamp-2">Exhaustive web search, source URLs, citations & benchmarks</p>
        </div>

        {/* Stage 2 Parallel Group: Spanning 2 Columns (Technical Writer & Diagram Architect) */}
        <div
          aria-current={stage2Running ? "step" : undefined}
          className={`md:col-span-2 p-4 rounded-xl border transition-all ${
            stage2Running
              ? "bg-accent/40 border-signal/60 shadow-lg shadow-indigo-500/15 ring-1 ring-signal/40"
              : stage2Done
              ? "bg-surface-raised/30 border-border/60 text-muted-foreground"
              : "bg-surface/40 border-border/50 text-muted-foreground opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-signal/20 text-signal border border-signal/30 flex items-center gap-1">
                <Zap className="w-3 h-3 text-amber-400" />
                STAGE 2 · CONCURRENT EXECUTION
              </span>
            </div>
            {stage2Running && (
              <span className="flex items-center gap-1.5 text-xs text-signal font-medium">
                <Loader2 className="w-3.5 h-3.5 text-signal animate-spin" />
                Executing in parallel
              </span>
            )}
            {stage2Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {/* Agent 2a: Technical Writer */}
            <div className={`p-3 rounded-lg border ${
              stage2Running
                ? "bg-surface/90 border-signal/30"
                : stage2Done
                ? "bg-surface/50 border-border"
                : "bg-background/40 border-border/40"
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className="p-1.5 rounded bg-signal/20 text-signal">
                  <PenTool className="w-3.5 h-3.5" />
                </div>
                <h5 className="text-xs font-semibold text-foreground">Technical Writer</h5>
              </div>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Authoring 2,500+ word deep-dive technical narrative
              </p>
            </div>

            {/* Agent 2b: Diagram Architect */}
            <div className={`p-3 rounded-lg border ${
              stage2Running
                ? "bg-surface/90 border-signal/30"
                : stage2Done
                ? "bg-surface/50 border-border"
                : "bg-background/40 border-border/40"
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className="p-1.5 rounded bg-signal/20 text-signal">
                  <GitFork className="w-3.5 h-3.5" />
                </div>
                <h5 className="text-xs font-semibold text-foreground">Diagram Architect</h5>
              </div>
              <p className="text-[11px] text-muted-foreground leading-snug">
                Synthesizing native Mermaid architecture & topologies
              </p>
            </div>
          </div>
        </div>

        {/* Stage 3: Editorial Director */}
        <div
          aria-current={stage3Current ? "step" : undefined}
          className={`p-4 rounded-xl border transition-all ${
            stage3Current
              ? "bg-accent/40 border-signal/50 shadow-lg shadow-indigo-500/10 ring-1 ring-signal/30"
              : stage3Done
              ? "bg-surface-raised/30 border-border/60 text-muted-foreground"
              : "bg-surface/40 border-border/50 text-muted-foreground opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div
              className={`p-2 rounded-lg ${
                stage3Current
                  ? "bg-accent text-white"
                  : stage3Done
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-surface-raised text-muted-foreground"
              }`}
            >
              <CheckCircle className="w-4 h-4" />
            </div>
            {stage3Current && <Loader2 className="w-4 h-4 text-signal animate-spin" />}
            {stage3Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-surface-raised text-foreground">STAGE 3</span>
          </div>
          <h4 className={`text-sm font-semibold mb-0.5 mt-1 ${stage3Current ? "text-foreground" : ""}`}>
            Editorial Director
          </h4>
          <p className="text-xs text-muted-foreground line-clamp-2">Integrates narrative & diagrams, quality audit, citations verification</p>
        </div>
      </div>

      {/* Live Agent Terminal / Thought Stream */}
      <div className="bg-background border border-border rounded-xl p-4 font-mono text-xs">
        <div className="flex items-center justify-between text-muted-foreground mb-2 border-b border-border/80 pb-2">
          <span>Agent Activity Ledger</span>
          <span className="text-[10px] text-muted-foreground">{logs.length} events logged</span>
        </div>
        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="Agent activity ledger"
          className="space-y-1.5 max-h-36 overflow-y-auto pr-2"
        >
          {logs.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2 text-foreground">
              <span className="text-muted-foreground select-none" aria-hidden="true">
                &gt;
              </span>
              <span className="text-signal uppercase text-[10px] tracking-wider shrink-0 mt-0.5">
                [{log.type}]
              </span>
              {log.agent && (
                <span className="text-signal text-[10px] shrink-0 font-semibold mt-0.5">
                  [{log.agent}]
                </span>
              )}
              <span className="text-foreground break-all">{log.detail || JSON.stringify(log)}</span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="text-muted-foreground italic">Squad agents initializing…</div>
          )}
        </div>
      </div>
    </div>
  );
}
