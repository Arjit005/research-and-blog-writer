"use client";

import React, { useMemo } from "react";
import type { DiffStats } from "@/lib/api";

interface DiffViewerProps {
  /** Server-generated diff markup (`diff_html` from the revisions API). */
  diffHtml?: string;
  /** Optional unified diff text fallback (e.g. `git diff` style patch). */
  patch?: string;
  stats?: DiffStats;
  fromRevision: number;
  toRevision: number;
  onClose?: () => void;
}

type DiffRowKind = "add" | "del" | "ctx" | "chunk" | "meta" | "empty";

interface DiffRow {
  kind: DiffRowKind;
  text: string;
}

const CLASS_TO_KIND: Record<string, DiffRowKind> = {
  "diff-add": "add",
  "diff-del": "del",
  "diff-ctx": "ctx",
  "diff-chunk": "chunk",
  "diff-meta": "meta",
  "diff-empty": "empty",
};

// Rows may carry multiple classes (e.g. `diff-line diff-add`), so the match is
// on the class list rather than an exact class string. The wrapper
// `diff-container` never matches because only the row classes are listed.
const DIFF_ROW_PATTERN =
  /<div class="([^"]*\bdiff-(?:add|del|ctx|chunk|meta|empty)\b[^"]*)">([\s\S]*?)<\/div>/g;

// `core/revisions.py` escapes every diff line with html.escape(), so only these
// five entities can appear in the text nodes of the returned markup.
const HTML_ENTITIES: Record<string, string> = {
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#x27;": "'",
};

function decodeEntities(text: string): string {
  return text.replace(/&(?:amp|lt|gt|quot|#x27);/g, (entity) => HTML_ENTITIES[entity] ?? entity);
}

/**
 * Parse the backend's diff markup into plain-text rows.
 *
 * This is intentionally an allowlist reader, NOT an HTML renderer: only
 * `<div class="...">text</div>` fragments are recognised, classes are mapped to
 * a fixed kind enum, inner tags are stripped and entities decoded. Everything
 * is rendered as React text children, so no markup (and no script) from the
 * API can ever be injected into the page.
 */
function parseDiffHtml(diffHtml: string): DiffRow[] {
  const rows: DiffRow[] = [];
  DIFF_ROW_PATTERN.lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = DIFF_ROW_PATTERN.exec(diffHtml)) !== null) {
    const classes = match[1].trim().split(/\s+/);
    const kind = classes.map((cls) => CLASS_TO_KIND[cls]).find((value): value is DiffRowKind => Boolean(value)) ?? "ctx";
    const text = decodeEntities(match[2].replace(/<[^>]*>/g, ""));
    rows.push({ kind, text });
  }

  return rows;
}

function parseUnifiedPatch(patch: string): DiffRow[] {
  return patch.split("\n").map((line): DiffRow => {
    if (line.startsWith("+++") || line.startsWith("---")) return { kind: "meta", text: line };
    if (line.startsWith("@@")) return { kind: "chunk", text: line };
    if (line.startsWith("+")) return { kind: "add", text: line };
    if (line.startsWith("-")) return { kind: "del", text: line };
    return { kind: "ctx", text: line };
  });
}

function rowClassName(kind: DiffRowKind): string {
  switch (kind) {
    case "add":
      return "bg-emerald-950/50 text-emerald-300 border-l-2 border-emerald-500 px-2 py-0.5 font-medium";
    case "del":
      return "bg-rose-950/50 text-rose-300 border-l-2 border-rose-500 px-2 py-0.5 line-through opacity-80";
    case "chunk":
      return "text-indigo-400 bg-indigo-950/30 px-2 py-1 my-1 rounded text-[11px]";
    case "meta":
      return "text-slate-500 px-2 py-0.5";
    case "empty":
      return "text-emerald-300 bg-emerald-950/30 px-3 py-2 rounded";
    default:
      return "text-slate-400 px-2 py-0.5";
  }
}

export function DiffViewer({ diffHtml, patch, stats, fromRevision, toRevision, onClose }: DiffViewerProps) {
  const rows = useMemo<DiffRow[]>(() => {
    if (diffHtml && diffHtml.trim()) {
      const parsed = parseDiffHtml(diffHtml);
      if (parsed.length > 0) return parsed;
    }
    if (patch && patch.trim()) {
      return parseUnifiedPatch(patch);
    }
    return [];
  }, [diffHtml, patch]);

  const statsLabel =
    stats && (stats.additions > 0 || stats.deletions > 0)
      ? `+${stats.additions} additions, −${stats.deletions} deletions`
      : null;

  return (
    <section
      aria-label={`Revision diff from revision ${fromRevision} to revision ${toRevision}`}
      className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl font-mono text-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 bg-slate-900 border-b border-slate-800">
        <span className="text-slate-400 font-sans font-medium">
          Revision Diff: Rev #{fromRevision} &rarr; Rev #{toRevision}
        </span>
        <div className="flex items-center gap-2">
          {statsLabel && (
            <span className="font-sans text-[11px] text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
              {statsLabel}
            </span>
          )}
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded bg-slate-800"
            >
              Close
            </button>
          )}
        </div>
      </div>

      <div className="p-4 overflow-x-auto max-h-[500px] overflow-y-auto divide-y divide-slate-900/50">
        {rows.length > 0 ? (
          rows.map((row, idx) => (
            <div key={idx} className={rowClassName(row.kind)}>
              <pre className="whitespace-pre-wrap break-all font-mono">{row.text}</pre>
            </div>
          ))
        ) : (
          <div className="text-slate-500 italic p-4 text-center">No structural changes between revisions.</div>
        )}
      </div>
    </section>
  );
}
