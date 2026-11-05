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
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
            </span>
            Active Hybrid Parallel Research Run
          </div>
          <h3 className="text-lg font-bold text-slate-100 line-clamp-1">{topic}</h3>
        </div>

        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/80 rounded-lg text-xs font-mono text-slate-300">
            <Clock className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
            <span>{elapsed}s elapsed</span>
          </div>

          {traceUrl && (
            <a
              href={traceUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-950/70 hover:bg-cyan-900 text-cyan-300 border border-cyan-800 rounded-lg text-xs font-medium transition"
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
              ? "bg-indigo-950/40 border-indigo-500/50 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30"
              : stage1Done
              ? "bg-slate-800/30 border-slate-700/60 text-slate-400"
              : "bg-slate-900/40 border-slate-800/50 text-slate-500 opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div
              className={`p-2 rounded-lg ${
                stage1Current
                  ? "bg-indigo-600 text-white"
                  : stage1Done
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-slate-800 text-slate-500"
              }`}
            >
              <Search className="w-4 h-4" />
            </div>
            {stage1Current && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />}
            {stage1Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">STAGE 1</span>
          </div>
          <h4 className={`text-sm font-semibold mb-0.5 mt-1 ${stage1Current ? "text-slate-100" : ""}`}>
            Lead Researcher
          </h4>
          <p className="text-xs text-slate-400 line-clamp-2">Exhaustive web search, source URLs, citations & benchmarks</p>
        </div>

        {/* Stage 2 Parallel Group: Spanning 2 Columns (Technical Writer & Diagram Architect) */}
        <div
          aria-current={stage2Running ? "step" : undefined}
          className={`md:col-span-2 p-4 rounded-xl border transition-all ${
            stage2Running
              ? "bg-indigo-950/40 border-indigo-500/60 shadow-lg shadow-indigo-500/15 ring-1 ring-indigo-500/40"
              : stage2Done
              ? "bg-slate-800/30 border-slate-700/60 text-slate-400"
              : "bg-slate-900/40 border-slate-800/50 text-slate-500 opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 flex items-center gap-1">
                <Zap className="w-3 h-3 text-amber-400" />
                STAGE 2 · CONCURRENT EXECUTION
              </span>
            </div>
            {stage2Running && (
              <span className="flex items-center gap-1.5 text-xs text-indigo-300 font-medium">
                <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
                Executing in parallel
              </span>
            )}
            {stage2Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {/* Agent 2a: Technical Writer */}
            <div className={`p-3 rounded-lg border ${
              stage2Running
                ? "bg-slate-900/90 border-indigo-500/30"
                : stage2Done
                ? "bg-slate-900/50 border-slate-800"
                : "bg-slate-950/40 border-slate-800/40"
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className="p-1.5 rounded bg-indigo-500/20 text-indigo-300">
                  <PenTool className="w-3.5 h-3.5" />
                </div>
                <h5 className="text-xs font-semibold text-slate-200">Technical Writer</h5>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
                Authoring 2,500+ word deep-dive technical narrative
              </p>
            </div>

            {/* Agent 2b: Diagram Architect */}
            <div className={`p-3 rounded-lg border ${
              stage2Running
                ? "bg-slate-900/90 border-indigo-500/30"
                : stage2Done
                ? "bg-slate-900/50 border-slate-800"
                : "bg-slate-950/40 border-slate-800/40"
            }`}>
              <div className="flex items-center gap-2 mb-1">
                <div className="p-1.5 rounded bg-cyan-500/20 text-cyan-300">
                  <GitFork className="w-3.5 h-3.5" />
                </div>
                <h5 className="text-xs font-semibold text-slate-200">Diagram Architect</h5>
              </div>
              <p className="text-[11px] text-slate-400 leading-snug">
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
              ? "bg-indigo-950/40 border-indigo-500/50 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30"
              : stage3Done
              ? "bg-slate-800/30 border-slate-700/60 text-slate-400"
              : "bg-slate-900/40 border-slate-800/50 text-slate-500 opacity-60"
          }`}
        >
          <div className="flex items-center justify-between mb-2">
            <div
              className={`p-2 rounded-lg ${
                stage3Current
                  ? "bg-indigo-600 text-white"
                  : stage3Done
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-slate-800 text-slate-500"
              }`}
            >
              <CheckCircle className="w-4 h-4" />
            </div>
            {stage3Current && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />}
            {stage3Done && <CheckCircle className="w-4 h-4 text-emerald-400" />}
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300">STAGE 3</span>
          </div>
          <h4 className={`text-sm font-semibold mb-0.5 mt-1 ${stage3Current ? "text-slate-100" : ""}`}>
            Editorial Director
          </h4>
          <p className="text-xs text-slate-400 line-clamp-2">Integrates narrative & diagrams, quality audit, citations verification</p>
        </div>
      </div>

      {/* Live Agent Terminal / Thought Stream */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs">
        <div className="flex items-center justify-between text-slate-400 mb-2 border-b border-slate-800/80 pb-2">
          <span>Agent Activity Ledger</span>
          <span className="text-[10px] text-slate-500">{logs.length} events logged</span>
        </div>
        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="Agent activity ledger"
          className="space-y-1.5 max-h-36 overflow-y-auto pr-2"
        >
          {logs.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2 text-slate-300">
              <span className="text-slate-500 select-none" aria-hidden="true">
                &gt;
              </span>
              <span className="text-indigo-400 uppercase text-[10px] tracking-wider shrink-0 mt-0.5">
                [{log.type}]
              </span>
              {log.agent && (
                <span className="text-cyan-400 text-[10px] shrink-0 font-semibold mt-0.5">
                  [{log.agent}]
                </span>
              )}
              <span className="text-slate-300 break-all">{log.detail || JSON.stringify(log)}</span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="text-slate-500 italic">Squad agents initializing…</div>
          )}
        </div>
      </div>
    </div>
  );
}
