"use client";

import React, { useState, useEffect } from "react";
import { api, RevisionSummary, DiffResult } from "@/lib/api";
import { DiffViewer } from "./diff-viewer";
import { X, History, GitCompare, RotateCcw, MessageSquare, Send, Loader2 } from "lucide-react";

interface CopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  articleId: number;
  onArticleRestored?: () => void;
}

export function CopilotDrawer({
  isOpen,
  onClose,
  articleId,
  onArticleRestored,
}: CopilotDrawerProps) {
  const [tab, setTab] = useState<"history" | "chat">("history");
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [activeDiff, setActiveDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  // Chat state
  const [messages, setMessages] = useState<Array<{ role: "user" | "assistant"; content: string }>>([
    {
      role: "assistant",
      content: "Hello! I am your AI Editorial Copilot. How can I assist you with refining this article?",
    },
  ]);
  const [input, setInput] = useState("");

  useEffect(() => {
    if (isOpen && articleId) {
      loadRevisions();
    }
  }, [isOpen, articleId]);

  const loadRevisions = async () => {
    setLoading(true);
    try {
      const data = await api.listRevisions(articleId);
      setRevisions(data);
    } catch (err) {
      console.error("Failed to load revisions:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async (fromRev: number, toRev: number) => {
    try {
      const diff = await api.getRevisionDiff(articleId, fromRev, toRev);
      setActiveDiff(diff);
    } catch (err) {
      console.error("Failed to fetch diff:", err);
    }
  };

  const handleRestore = async (revisionId: number) => {
    if (!confirm("Are you sure you want to restore this revision? A new revision will be created.")) return;
    setRestoring(revisionId);
    try {
      await api.restoreRevision(articleId, revisionId);
      await loadRevisions();
      if (onArticleRestored) onArticleRestored();
    } catch (err) {
      console.error("Restore failed:", err);
    } finally {
      setRestoring(null);
    }
  };

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMsg = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);
    setInput("");

    // Simulated responsive feedback
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `To implement "${userMsg}", you can review the suggested changes in the diff view or request a specific rewrite section.`,
        },
      ]);
    }, 600);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col text-slate-100">
      {/* Drawer Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <button
            onClick={() => { setTab("history"); setActiveDiff(null); }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              tab === "history" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <History className="w-3.5 h-3.5" />
            Revision Timeline
          </button>
          <button
            onClick={() => setTab("chat")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              tab === "chat" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" />
            Copilot Chat
          </button>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Drawer Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "history" ? (
          <div>
            {activeDiff ? (
              <DiffViewer
                patch={activeDiff.diff_patch}
                fromRevision={activeDiff.from_revision}
                toRevision={activeDiff.to_revision}
                onClose={() => setActiveDiff(null)}
              />
            ) : (
              <div className="space-y-3">
                <div className="text-xs text-slate-400 mb-2">
                  Track full version history, inspect code diffs, or restore any checkpoint.
                </div>

                {loading && (
                  <div className="flex items-center justify-center p-8 text-slate-500">
                    <Loader2 className="w-6 h-6 animate-spin" />
                  </div>
                )}

                {revisions.map((rev, idx) => (
                  <div
                    key={rev.id}
                    className="p-3.5 rounded-xl border border-slate-800 bg-slate-950/60 hover:border-slate-700 transition"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="px-2 py-0.5 text-[11px] font-mono font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded">
                        Rev #{rev.revision_num}
                      </span>
                      <span className="text-[11px] text-slate-500">{rev.created_at}</span>
                    </div>

                    <p className="text-xs text-slate-200 font-medium mb-3">{rev.summary}</p>

                    <div className="flex items-center gap-2">
                      {idx < revisions.length - 1 && (
                        <button
                          onClick={() => handleCompare(revisions[idx + 1].revision_num, rev.revision_num)}
                          className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
                        >
                          <GitCompare className="w-3 h-3" />
                          Compare Prev
                        </button>
                      )}

                      <button
                        onClick={() => handleRestore(rev.id)}
                        disabled={restoring === rev.id}
                        className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
                      >
                        {restoring === rev.id ? (
                          <Loader2 className="w-3 h-3 animate-spin" />
                        ) : (
                          <RotateCcw className="w-3 h-3 text-amber-400" />
                        )}
                        Restore
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col h-full">
            <div className="flex-1 space-y-3 overflow-y-auto pr-1">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`p-3 rounded-2xl text-xs max-w-[85%] ${
                    m.role === "user"
                      ? "ml-auto bg-indigo-600 text-white"
                      : "bg-slate-800/80 border border-slate-700/60 text-slate-200"
                  }`}
                >
                  {m.content}
                </div>
              ))}
            </div>

            <form onSubmit={handleSendMessage} className="mt-4 flex gap-2">
              <input
                type="text"
                placeholder="Ask Copilot to polish, summarize, or fix..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                type="submit"
                disabled={!input.trim()}
                className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl transition"
              >
                <Send className="w-4 h-4" />
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
