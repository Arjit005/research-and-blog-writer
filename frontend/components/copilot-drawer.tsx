"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { api, errorMessage, RevisionSummary, DiffResult } from "@/lib/api";
import { DiffViewer } from "./diff-viewer";
import {
  X,
  History,
  GitCompare,
  RotateCcw,
  MessageSquare,
  Send,
  Loader2,
  Sparkles,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";

interface CopilotDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  articleId: number;
  onArticleRestored?: () => void;
  onArticleUpdated?: () => void;
}

interface CopilotMessage {
  role: "user" | "assistant";
  content: string;
}

interface AppliedEdit {
  revisionNum: number;
  content: string;
  instruction: string;
}

const INITIAL_MESSAGE =
  "Ask me to polish, restructure, shorten, or rewrite a section. Your instruction is sent to the backend editorial endpoint (POST /api/v1/articles/{id}/edit) and creates a new revision.";

const previewComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-sm font-bold text-slate-100 mt-3 mb-1">{children}</h3>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-sm font-bold text-slate-100 mt-3 mb-1">{children}</h3>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h4 className="text-xs font-semibold text-slate-200 mt-2 mb-1">{children}</h4>
  ),
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-2">{children}</p>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="list-disc pl-4 mb-2">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="list-decimal pl-4 mb-2">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li className="mb-0.5">{children}</li>,
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
    <a href={href} className="text-indigo-400 underline" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
};

export function CopilotDrawer({
  isOpen,
  onClose,
  articleId,
  onArticleRestored,
  onArticleUpdated,
}: CopilotDrawerProps) {
  const [tab, setTab] = useState<"history" | "chat">("history");
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [activeDiff, setActiveDiff] = useState<DiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [restoring, setRestoring] = useState<number | null>(null);

  // Chat / copilot edit state
  const [messages, setMessages] = useState<CopilotMessage[]>([{ role: "assistant", content: INITIAL_MESSAGE }]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [editResult, setEditResult] = useState<AppliedEdit | null>(null);
  const [panelError, setPanelError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  const loadRevisions = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.listRevisions(articleId);
      setRevisions(data);
      setPanelError(null);
    } catch (err) {
      console.error("Failed to load revisions:", err);
      setPanelError(errorMessage(err, "Could not load the revision history."));
    } finally {
      setLoading(false);
    }
  }, [articleId]);

  useEffect(() => {
    if (isOpen && articleId) {
      void loadRevisions();
    }
  }, [isOpen, articleId, loadRevisions]);

  const handleCompare = async (fromRev: number, toRev: number) => {
    setPanelError(null);
    try {
      const diff = await api.getRevisionDiff(articleId, fromRev, toRev);
      setActiveDiff(diff);
    } catch (err) {
      console.error("Failed to fetch diff:", err);
      setPanelError(errorMessage(err, "Could not load the diff between those revisions."));
    }
  };

  const handleRestore = async (revisionNum: number) => {
    if (!window.confirm("Restore this revision? A new revision with the current content will be snapshotted first.")) {
      return;
    }
    setRestoring(revisionNum);
    setPanelError(null);
    try {
      await api.restoreRevision(articleId, revisionNum);
      await loadRevisions();
      onArticleRestored?.();
    } catch (err) {
      console.error("Restore failed:", err);
      setPanelError(errorMessage(err, "Restore failed. Please try again."));
    } finally {
      setRestoring(null);
    }
  };

  const handleSendMessage = async (event: React.FormEvent) => {
    event.preventDefault();
    const instruction = input.trim();
    if (!instruction || sending) return;

    setMessages((prev) => [...prev, { role: "user", content: instruction }]);
    setInput("");
    setSending(true);
    setPanelError(null);
    setEditResult(null);

    try {
      const result = await api.applyCopilotEdit({ article_id: articleId, instruction });
      if (!result.success) {
        throw new Error("The editorial copilot could not apply this edit.");
      }

      setEditResult({ revisionNum: result.new_revision_num, content: result.content, instruction });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Done — revision #${result.new_revision_num} was created from your instruction. Preview it below.`,
        },
      ]);
      await loadRevisions();
      onArticleUpdated?.();
    } catch (err) {
      console.error("Copilot edit failed:", err);
      const message = errorMessage(err, "The copilot edit failed. The backend edit endpoint may be unavailable.");
      setPanelError(message);
      setMessages((prev) => [...prev, { role: "assistant", content: `I could not apply that edit: ${message}` }]);
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  if (!isOpen) return null;

  return (
    <aside
      role="dialog"
      aria-label="Revision history and AI editorial copilot"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-lg bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col text-slate-100"
    >
      {/* Drawer Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-800">
        <div className="flex items-center gap-2" role="tablist" aria-label="Copilot panels">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "history"}
            aria-controls="copilot-history-panel"
            onClick={() => {
              setTab("history");
              setActiveDiff(null);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              tab === "history" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <History className="w-3.5 h-3.5" aria-hidden="true" />
            Revision Timeline
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "chat"}
            aria-controls="copilot-chat-panel"
            onClick={() => setTab("chat")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition ${
              tab === "chat" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5" aria-hidden="true" />
            Copilot Chat
          </button>
        </div>

        <button
          type="button"
          onClick={onClose}
          aria-label="Close revision and copilot panel"
          className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" aria-hidden="true" />
        </button>
      </div>

      {panelError && (
        <div
          role="alert"
          className="mx-4 mt-3 flex items-start gap-2 rounded-xl border border-rose-500/30 bg-rose-500/10 p-3 text-xs text-rose-300"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <span>{panelError}</span>
        </div>
      )}

      {/* Drawer Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "history" ? (
          <div id="copilot-history-panel" role="tabpanel" aria-label="Revision timeline">
            {activeDiff ? (
              <DiffViewer
                diffHtml={activeDiff.diff_html}
                stats={activeDiff.stats}
                fromRevision={activeDiff.from_revision}
                toRevision={activeDiff.to_revision}
                onClose={() => setActiveDiff(null)}
              />
            ) : (
              <div className="space-y-3">
                <p className="text-xs text-slate-400 mb-2">
                  Track version history, inspect saved diffs, or restore any checkpoint. Restore targets the
                  revision number, not the database row id.
                </p>

                {loading && (
                  <div className="flex items-center justify-center p-8 text-slate-500">
                    <Loader2 className="w-6 h-6 animate-spin" aria-label="Loading revisions" />
                  </div>
                )}

                {!loading && revisions.length === 0 && (
                  <p className="p-4 text-center text-xs text-slate-500 italic">No revisions recorded yet.</p>
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
                          type="button"
                          onClick={() => void handleCompare(revisions[idx + 1].revision_num, rev.revision_num)}
                          className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-[11px] font-medium transition"
                        >
                          <GitCompare className="w-3 h-3" aria-hidden="true" />
                          Compare Prev
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => void handleRestore(rev.revision_num)}
                        disabled={restoring === rev.revision_num}
                        aria-label={`Restore revision ${rev.revision_num}`}
                        className="flex items-center gap-1 px-2.5 py-1 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-300 rounded text-[11px] font-medium transition"
                      >
                        {restoring === rev.revision_num ? (
                          <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
                        ) : (
                          <RotateCcw className="w-3 h-3 text-amber-400" aria-hidden="true" />
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
          <div id="copilot-chat-panel" role="tabpanel" aria-label="Copilot chat" className="flex flex-col h-full">
            <div
              role="log"
              aria-live="polite"
              aria-relevant="additions text"
              aria-label="Copilot conversation"
              className="flex-1 space-y-3 overflow-y-auto pr-1"
            >
              {messages.map((message, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-2xl text-xs max-w-[85%] ${
                    message.role === "user"
                      ? "ml-auto bg-indigo-600 text-white"
                      : "bg-slate-800/80 border border-slate-700/60 text-slate-200"
                  }`}
                >
                  {message.content}
                </div>
              ))}

              {sending && (
                <div className="flex items-center gap-2 p-3 text-xs text-slate-400">
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                  Applying your instruction…
                </div>
              )}
            </div>

            {editResult && (
              <section
                aria-live="polite"
                aria-label="Applied edit preview"
                className="mt-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-3"
              >
                <div className="flex items-center gap-2 text-xs font-semibold text-emerald-300 mb-2">
                  <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
                  Applied — Rev #{editResult.revisionNum}
                </div>
                <p className="text-[11px] text-slate-400 mb-2 break-words">
                  Instruction: <span className="text-slate-300">{editResult.instruction}</span>
                </p>
                <div className="max-h-64 overflow-y-auto rounded-xl bg-slate-950/70 border border-slate-800 p-3 text-xs text-slate-300 leading-relaxed">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={previewComponents}
                  >
                    {editResult.content}
                  </ReactMarkdown>
                </div>
              </section>
            )}

            <form onSubmit={handleSendMessage} className="mt-4 flex gap-2">
              <label htmlFor="copilot-instruction" className="sr-only">
                Instruction for the editorial copilot
              </label>
              <input
                id="copilot-instruction"
                ref={inputRef}
                type="text"
                placeholder="Ask Copilot to polish, summarize, or fix…"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={sending}
                className="flex-1 px-3 py-2 bg-slate-800 border border-slate-700 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
              />
              <button
                type="submit"
                disabled={!input.trim() || sending}
                aria-label="Send instruction to the editorial copilot"
                className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl transition"
              >
                {sending ? (
                  <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Send className="w-4 h-4" aria-hidden="true" />
                )}
              </button>
            </form>
            <p className="mt-2 flex items-center gap-1 text-[10px] text-slate-500">
              <Sparkles className="w-3 h-3" aria-hidden="true" />
              Creates a real revision via the backend edit endpoint.
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
