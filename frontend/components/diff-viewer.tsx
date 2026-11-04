"use client";

import React from "react";

interface DiffViewerProps {
  patch: string;
  fromRevision: number;
  toRevision: number;
  onClose?: () => void;
}

export function DiffViewer({ patch, fromRevision, toRevision, onClose }: DiffViewerProps) {
  const lines = patch.split("\n");

  return (
    <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl font-mono text-xs">
      <div className="flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="text-slate-400 font-sans font-medium">
            Revision Diff: Rev #{fromRevision} &rarr; Rev #{toRevision}
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded bg-slate-800"
          >
            Close
          </button>
        )}
      </div>

      <div className="p-4 overflow-x-auto max-h-[500px] overflow-y-auto divide-y divide-slate-900/50">
        {lines.map((line, idx) => {
          let style = "text-slate-400 px-2 py-0.5";
          if (line.startsWith("+") && !line.startsWith("+++")) {
            style = "bg-emerald-950/50 text-emerald-300 border-l-2 border-emerald-500 px-2 py-0.5 font-medium";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            style = "bg-rose-950/50 text-rose-300 border-l-2 border-rose-500 px-2 py-0.5 line-through opacity-80";
          } else if (line.startsWith("@@")) {
            style = "text-indigo-400 bg-indigo-950/30 px-2 py-1 my-1 rounded text-[11px]";
          }

          return (
            <div key={idx} className={style}>
              <pre className="whitespace-pre-wrap break-all">{line}</pre>
            </div>
          );
        })}
        {lines.length === 0 && (
          <div className="text-slate-500 italic p-4 text-center">No structural changes between revisions.</div>
        )}
      </div>
    </div>
  );
}
