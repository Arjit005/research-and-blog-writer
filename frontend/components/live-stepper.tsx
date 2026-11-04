"use client";

import React, { useEffect, useState } from "react";
import { Search, PenTool, GitFork, CheckCircle, Loader2, XCircle, Clock, Zap } from "lucide-react";

interface LiveStepperProps {
  runId: string;
  topic: string;
  onCancel?: () => void;
  logs: Array<{ type: string; detail?: string; timestamp?: number }>;
  stage: number;
}

const STAGES = [
  { id: 1, name: "Lead Researcher", desc: "Searching web, synthesizing citations & facts", icon: Search },
  { id: 2, name: "Technical Writer", desc: "Drafting comprehensive authoritative article", icon: PenTool },
  { id: 3, name: "Diagram Architect", desc: "Synthesizing Mermaid.js architectural visual", icon: GitFork },
  { id: 4, name: "Editorial Director", desc: "Polishing tone, readability & structure", icon: CheckCircle },
];

export function LiveStepper({ runId, topic, onCancel, logs, stage }: LiveStepperProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const latestLog = logs.length > 0 ? logs[logs.length - 1] : null;

  return (
    <div className="w-full bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md">
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold text-indigo-400 uppercase tracking-wider mb-1">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500"></span>
            </span>
            Active Research Run
          </div>
          <h3 className="text-lg font-bold text-slate-100 line-clamp-1">{topic}</h3>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/80 rounded-lg text-xs font-mono text-slate-300">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>{elapsed}s elapsed</span>
          </div>

          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800/80 rounded-lg text-xs font-mono text-slate-300">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            <span>~{Math.round(elapsed * 45)} tokens</span>
          </div>

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

      {/* 4-Stage Stepper Track */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 my-6">
        {STAGES.map((s) => {
          const Icon = s.icon;
          const isDone = stage > s.id;
          const isCurrent = stage === s.id;
          const isPending = stage < s.id;

          return (
            <div
              key={s.id}
              className={`p-4 rounded-xl border transition-all ${
                isCurrent
                  ? "bg-indigo-950/40 border-indigo-500/50 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30"
                  : isDone
                  ? "bg-slate-800/30 border-slate-700/60 text-slate-400"
                  : "bg-slate-900/40 border-slate-800/50 text-slate-500 opacity-60"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <div
                  className={`p-2 rounded-lg ${
                    isCurrent
                      ? "bg-indigo-600 text-white"
                      : isDone
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                      : "bg-slate-800 text-slate-500"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                </div>
                {isCurrent && <Loader2 className="w-4 h-4 text-indigo-400 animate-spin" />}
                {isDone && <CheckCircle className="w-4 h-4 text-emerald-400" />}
              </div>
              <h4 className={`text-sm font-semibold mb-0.5 ${isCurrent ? "text-slate-100" : ""}`}>
                {s.name}
              </h4>
              <p className="text-xs text-slate-400 line-clamp-2">{s.desc}</p>
            </div>
          );
        })}
      </div>

      {/* Live Agent Terminal / Thought Stream */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs">
        <div className="flex items-center justify-between text-slate-400 mb-2 border-b border-slate-800/80 pb-2">
          <span>Agent Activity Ledger</span>
          <span className="text-[10px] text-slate-500">{logs.length} events logged</span>
        </div>
        <div className="space-y-1.5 max-h-36 overflow-y-auto pr-2">
          {logs.map((log, idx) => (
            <div key={idx} className="flex items-start gap-2 text-slate-300">
              <span className="text-slate-500 select-none">&gt;</span>
              <span className="text-indigo-400 uppercase text-[10px] tracking-wider shrink-0 mt-0.5">
                [{log.type}]
              </span>
              <span className="text-slate-300 break-all">{log.detail || JSON.stringify(log)}</span>
            </div>
          ))}
          {logs.length === 0 && (
            <div className="text-slate-500 italic">Squad agents initializing...</div>
          )}
        </div>
      </div>
    </div>
  );
}
