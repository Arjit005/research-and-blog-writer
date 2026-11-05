"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  errorMessage,
  User,
  ArticleSummary,
  ArticleDetail,
  TelemetryStats,
} from "@/lib/api";
import { ResumableSSEClient, SSEPayload } from "@/lib/sse";
import { AuthDialog } from "@/components/auth-dialog";
import { LiveStepper } from "@/components/live-stepper";
import { ArticleViewer } from "@/components/article-viewer";
import { CopilotDrawer } from "@/components/copilot-drawer";
import { ApiKeysDialog } from "@/components/api-keys-dialog";
import {
  Sparkles,
  BookOpen,
  SlidersHorizontal,
  ChevronDown,
  Database,
  LogOut,
  UserCheck,
  Key,
} from "lucide-react";

const PRESET_TOPICS = [
  "Autonomous Multi-Agent AI Systems: 2026 Architecture",
  "Quantum Computing Advancements in Post-RSA Cryptography",
  "High-Throughput Event-Driven Microservices in Rust & Go",
  "Zero-Knowledge Proofs in Enterprise Cloud Security",
];

// Persisted so a page refresh mid-run reattaches to the existing backend job
// instead of letting the UI dead-end (the backend enforces one active run/user).
const ACTIVE_RUN_STORAGE_KEY = "research-studio:active-run";

interface StoredRun {
  runId: string;
  topic: string;
}

function readStoredRun(): StoredRun | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_RUN_STORAGE_KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      typeof parsed === "object" &&
      parsed !== null &&
      typeof (parsed as Record<string, unknown>).runId === "string" &&
      typeof (parsed as Record<string, unknown>).topic === "string"
    ) {
      const record = parsed as Record<string, unknown>;
      return { runId: record.runId as string, topic: record.topic as string };
    }
  } catch (err) {
    console.error("Could not read stored research run:", err);
  }
  return null;
}

function writeStoredRun(run: StoredRun): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, JSON.stringify(run));
  } catch (err) {
    console.error("Could not persist research run:", err);
  }
}

function clearStoredRun(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
  } catch (err) {
    console.error("Could not clear stored research run:", err);
  }
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export default function Home() {
  const [user, setUser] = useState<User | null>(null);
  const [isAuthOpen, setIsAuthOpen] = useState(false);
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [selectedArticle, setSelectedArticle] = useState<ArticleDetail | null>(null);

  // Prompt configuration
  const [topic, setTopic] = useState("");
  const [tone, setTone] = useState("Professional & Authoritative");
  const [audience, setAudience] = useState("Software Engineers & Developers");
  const [targetLength, setTargetLength] = useState("Standard Blog (1,500 - 2,000 words)");
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Active run state
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeTopic, setActiveTopic] = useState("");
  const [runLogs, setRunLogs] = useState<Array<{ type: string; detail?: string; timestamp?: number }>>([]);
  const [runStage, setRunStage] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [activeTraceUrl, setActiveTraceUrl] = useState<string | null>(null);
  const [isApiKeysOpen, setIsApiKeysOpen] = useState(false);

  // Copilot Drawer
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);

  // System status
  const [systemStats, setSystemStats] = useState<TelemetryStats | null>(null);

  const sseClientRef = useRef<ResumableSSEClient | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const selectedArticleRef = useRef<ArticleDetail | null>(null);

  useEffect(() => {
    selectedArticleRef.current = selectedArticle;
  }, [selectedArticle]);

  useEffect(() => {
    activeRunIdRef.current = activeRunId;
  }, [activeRunId]);

  const closeStream = useCallback(() => {
    if (sseClientRef.current) {
      sseClientRef.current.close();
      sseClientRef.current = null;
    }
  }, []);

  const loadArticleDetail = useCallback(async (id: number) => {
    try {
      const article = await api.getArticle(id);
      setSelectedArticle(article);
    } catch (err) {
      console.error("Failed to fetch article detail:", err);
    }
  }, []);

  const loadArticles = useCallback(async () => {
    try {
      const list = await api.listArticles();
      const safeArticles = Array.isArray(list) ? list : [];
      setArticles(safeArticles);
      if (safeArticles.length > 0 && !selectedArticleRef.current && !activeRunIdRef.current) {
        await loadArticleDetail(safeArticles[0].id);
      }
    } catch (err) {
      console.error("Failed to load articles:", err);
      setArticles([]);
    }
  }, [loadArticleDetail]);

  const loadTelemetry = useCallback(async () => {
    try {
      const stats = await api.getTelemetryStats();
      setSystemStats(stats);
    } catch (err) {
      console.error("Failed to fetch telemetry:", err);
    }
  }, []);

  const handleRunCompleted = useCallback(
    async (data: SSEPayload | Record<string, unknown>) => {
      setRunStage(4);
      const traceUrl = asString(data.trace_url);
      if (traceUrl) setActiveTraceUrl(traceUrl);

      const articleId = asNumber(data.article_id);
      setActiveRunId(null);
      activeRunIdRef.current = null;
      clearStoredRun();
      closeStream();

      await loadArticles();
      if (articleId) {
        await loadArticleDetail(articleId);
      }
    },
    [closeStream, loadArticles, loadArticleDetail]
  );

  /**
   * Reconcile through GET /runs/{id} when the SSE stream errors or exhausts its
   * reconnect budget: the job may have finished while the socket was down.
   */
  const handleStreamError = useCallback(
    async (error: Error) => {
      setRunError(error.message);
      const runId = activeRunIdRef.current;
      if (!runId) return;

      try {
        const status = await api.getRunStatus(runId);
        if (status.status === "completed") {
          await handleRunCompleted({
            article_id: status.result_article_id ?? undefined,
            trace_url: status.trace_url ?? undefined,
          });
          return;
        }
        if (status.status === "failed") {
          setRunError(status.error_message || error.message);
          setActiveRunId(null);
          activeRunIdRef.current = null;
          clearStoredRun();
          closeStream();
          return;
        }
        if (status.status === "cancelled") {
          setRunError("Research run was cancelled.");
          setActiveRunId(null);
          activeRunIdRef.current = null;
          clearStoredRun();
          closeStream();
          return;
        }

        // Still running/pending server-side: keep the stepper usable (Cancel works)
        // and tell the truth instead of pretending the run is dead.
        setRunError(
          `${error.message} The server still reports this run as "${status.status}" — wait for it, or cancel and start again.`
        );
      } catch (err) {
        console.error("Run state reconciliation failed:", err);
        setActiveRunId(null);
        activeRunIdRef.current = null;
        clearStoredRun();
        closeStream();
      }
    },
    [handleRunCompleted, closeStream]
  );

  const attachToRun = useCallback(
    (runId: string, runTopic: string) => {
      closeStream();

      activeRunIdRef.current = runId;
      setActiveRunId(runId);
      setActiveTopic(runTopic);
      setSelectedArticle(null);
      selectedArticleRef.current = null;
      setRunStage(1);
      setRunLogs([]);
      setActiveTraceUrl(null);
      setRunError(null);
      writeStoredRun({ runId, topic: runTopic });

      const sse = new ResumableSSEClient(
        runId,
        (event) => {
          if (event.type === "step") {
            setRunLogs((prev) => [
              ...prev,
              { type: "step", detail: asString(event.data.detail), timestamp: asNumber(event.data.timestamp) },
            ]);
          } else if (event.type === "task_done") {
            setRunStage((current) => Math.min(current + 1, 4));
            setRunLogs((prev) => [
              ...prev,
              { type: "stage_complete", detail: "Stage finished", timestamp: asNumber(event.data.timestamp) },
            ]);
          } else if (event.type === "status") {
            setRunLogs((prev) => [
              ...prev,
              { type: "status", detail: asString(event.data.stage), timestamp: Date.now() },
            ]);
          }
        },
        (error) => {
          void handleStreamError(error);
        },
        (data) => {
          void handleRunCompleted(data);
        }
      );

      sseClientRef.current = sse;
      sse.connect();
    },
    [closeStream, handleStreamError, handleRunCompleted]
  );

  const restoreActiveRun = useCallback(async () => {
    const stored = readStoredRun();
    if (!stored) return;

    try {
      const status = await api.getRunStatus(stored.runId);
      if (status.status === "running" || status.status === "pending") {
        attachToRun(status.run_id, status.topic || stored.topic);
        return;
      }
      if (status.status === "completed") {
        await handleRunCompleted({
          article_id: status.result_article_id ?? undefined,
          trace_url: status.trace_url ?? undefined,
        });
        return;
      }
      if (status.status === "failed") {
        setRunError(status.error_message || "The previous research run failed.");
      }
      clearStoredRun();
    } catch (err) {
      // 404 (deleted run / different user) or transient auth issue: drop the pointer.
      console.error("Could not reattach to stored research run:", err);
      clearStoredRun();
    }
  }, [attachToRun, handleRunCompleted]);

  // Boot: restore session, then reconcile any run persisted before a refresh.
  useEffect(() => {
    let cancelled = false;

    const boot = async () => {
      try {
        const currentUser = await api.getMe();
        if (cancelled) return;
        setUser(currentUser);
        await loadArticles();
        await loadTelemetry();
        if (!cancelled) await restoreActiveRun();
      } catch {
        if (!cancelled) setIsAuthOpen(true);
      }
    };

    void boot();

    return () => {
      cancelled = true;
      closeStream();
    };
  }, [loadArticles, loadTelemetry, restoreActiveRun, closeStream]);

  const handleStartRun = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!topic.trim()) return;

    if (!user) {
      setIsAuthOpen(true);
      return;
    }

    setIsSubmitting(true);
    try {
      const runRes = await api.createRun({
        topic: topic.trim(),
        tone,
        audience,
        target_length: targetLength,
      });
      attachToRun(runRes.run_id, runRes.topic);
    } catch (err) {
      setRunError(errorMessage(err, "Failed to start run."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelRun = async () => {
    const runId = activeRunIdRef.current;
    if (!runId) return;
    try {
      await api.cancelRun(runId);
      closeStream();
      setActiveRunId(null);
      activeRunIdRef.current = null;
      clearStoredRun();
      setRunError("Research run was cancelled.");
    } catch (err) {
      console.error("Cancel failed:", err);
      setRunError(errorMessage(err, "Cancel failed. The run may still be active."));
    }
  };

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.error("Logout failed:", err);
    }
    closeStream();
    setUser(null);
    setArticles([]);
    setSelectedArticle(null);
    setActiveRunId(null);
    activeRunIdRef.current = null;
    clearStoredRun();
    setIsAuthOpen(true);
  };

  const databaseBackend = systemStats?.database.backend;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500/30">
      {/* 1. Studio Header */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-tr from-indigo-600 to-violet-600 rounded-xl shadow-lg shadow-indigo-500/20">
            <Sparkles className="w-5 h-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Research & Visual Blog Studio
              <span className="px-2 py-0.5 text-[10px] uppercase font-mono font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md">
                Next.js 16 · FastAPI
              </span>
            </h1>
            <p className="text-xs text-slate-400">Autonomous 4-Agent Research Squad & Native Mermaid Canvas</p>
          </div>
        </div>

        {/* System & User Badges */}
        <div className="flex items-center gap-3">
          {systemStats && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300">
              <Database className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
              <span>{databaseBackend ? databaseBackend.toUpperCase() : "DB"}</span>
              <span className="text-slate-600">|</span>
              <span className="text-slate-400">
                Cache hits: {systemStats.cache.metrics.total_hits ?? 0}
              </span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setIsApiKeysOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 rounded-xl text-xs text-slate-300 transition"
            title="Configure API Keys (Gemini / OpenRouter)"
          >
            <Key className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />
            <span className="hidden sm:inline">API Keys</span>
          </button>

          {user ? (
            <div className="flex items-center gap-2 pl-2">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl text-xs">
                <UserCheck className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />
                <span className="text-slate-300 font-medium">{user.email}</span>
              </div>
              <button
                type="button"
                onClick={() => void handleLogout()}
                title="Log out"
                aria-label="Log out"
                className="p-2 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-xl transition"
              >
                <LogOut className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsAuthOpen(true)}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold transition shadow-md shadow-indigo-600/20"
            >
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* 2. Main Studio Workspace Layout */}
      <div className="flex-1 flex flex-col lg:flex-row w-full max-w-[1600px] mx-auto p-4 md:p-8 gap-8">
        {/* Left Column: Prompt Input & Articles Library */}
        <div className="w-full lg:w-96 shrink-0 flex flex-col gap-6">
          {/* Research Prompt Composer Box */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-sm">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-indigo-400" aria-hidden="true" />
              Commission AI Squad
            </h2>

            <form onSubmit={handleStartRun} className="space-y-4">
              <div>
                <label htmlFor="research-topic" className="sr-only">
                  Research topic
                </label>
                <textarea
                  id="research-topic"
                  required
                  rows={3}
                  placeholder="Enter research topic, target domain, or prompt brief…"
                  value={topic}
                  onChange={(event) => setTopic(event.target.value)}
                  className="w-full p-3.5 bg-slate-950 border border-slate-800 rounded-2xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-200 resize-none placeholder:text-slate-500"
                />
              </div>

              {/* Quick Presets */}
              <div>
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                  Suggested Topics
                </span>
                <div className="flex flex-col gap-1.5">
                  {PRESET_TOPICS.map((preset, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setTopic(preset)}
                      className="text-left px-2.5 py-1.5 bg-slate-950 hover:bg-slate-800/80 text-slate-300 hover:text-white rounded-lg text-xs truncate transition border border-slate-800/60"
                    >
                      {preset}
                    </button>
                  ))}
                </div>
              </div>

              {/* Advanced Controls Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  aria-expanded={showAdvanced}
                  className="flex items-center justify-between w-full py-1.5 text-xs text-slate-400 hover:text-slate-200 transition"
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <SlidersHorizontal className="w-3.5 h-3.5" aria-hidden="true" />
                    Tone & Audience Options
                  </span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
                    aria-hidden="true"
                  />
                </button>

                {showAdvanced && (
                  <div className="pt-3 space-y-3 border-t border-slate-800 mt-2">
                    <div>
                      <label htmlFor="tone-select" className="block text-[11px] text-slate-400 mb-1">
                        Tone of Voice
                      </label>
                      <select
                        id="tone-select"
                        value={tone}
                        onChange={(event) => setTone(event.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200"
                      >
                        <option>Professional & Authoritative</option>
                        <option>Engaging & Accessible</option>
                        <option>Academic & Rigorous</option>
                        <option>Executive Brief</option>
                      </select>
                    </div>

                    <div>
                      <label htmlFor="audience-select" className="block text-[11px] text-slate-400 mb-1">
                        Target Audience
                      </label>
                      <select
                        id="audience-select"
                        value={audience}
                        onChange={(event) => setAudience(event.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200"
                      >
                        <option>Software Engineers & Developers</option>
                        <option>CTOs & Tech Leaders</option>
                        <option>Product Managers</option>
                        <option>General Tech Enthusiasts</option>
                      </select>
                    </div>

                    <div>
                      <label htmlFor="target-length-select" className="block text-[11px] text-slate-400 mb-1">
                        Target Length
                      </label>
                      <select
                        id="target-length-select"
                        value={targetLength}
                        onChange={(event) => setTargetLength(event.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200"
                      >
                        <option>Quick Brief (800 - 1,200 words)</option>
                        <option>Standard Blog (1,500 - 2,000 words)</option>
                        <option>Deep Dive (2,500 - 3,500 words)</option>
                      </select>
                    </div>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={isSubmitting || !!activeRunId || !topic.trim()}
                className="w-full py-3 px-4 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 text-white font-semibold rounded-2xl text-xs transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
              >
                <Sparkles className="w-4 h-4" aria-hidden="true" />
                {isSubmitting ? "Launching Squad…" : "Launch Research Squad"}
              </button>
            </form>

            {runError && (
              <div
                role="alert"
                className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400 space-y-2"
              >
                <div>{runError}</div>
                {(runError.includes("429") ||
                  runError.toLowerCase().includes("rate limit") ||
                  runError.includes("free-models-per-day")) && (
                  <button
                    type="button"
                    onClick={() => setIsApiKeysOpen(true)}
                    className="w-full py-2 px-3 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 font-medium rounded-lg text-xs transition flex items-center justify-center gap-1.5 shadow-sm"
                  >
                    <span>✨ Configure Free Gemini Key (1,500 req/day)</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Past Articles Library */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-sm flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
                Your Articles Library ({articles.length})
              </h3>
            </div>

            <div className="space-y-2 overflow-y-auto max-h-96 pr-1 divide-y divide-slate-800/40">
              {articles.map((article) => (
                <button
                  key={article.id}
                  type="button"
                  onClick={() => void loadArticleDetail(article.id)}
                  aria-pressed={selectedArticle?.id === article.id}
                  className={`w-full text-left pt-2 cursor-pointer p-3 rounded-xl transition ${
                    selectedArticle?.id === article.id
                      ? "bg-indigo-950/40 border border-indigo-500/40 text-slate-100"
                      : "hover:bg-slate-800/40 text-slate-300"
                  }`}
                >
                  <h4 className="text-xs font-semibold line-clamp-1 mb-1">{article.topic}</h4>
                  <div className="flex items-center gap-2 text-[10px] text-slate-500">
                    <span>{article.word_count.toLocaleString()} words</span>
                    <span>&bull;</span>
                    <span>{article.created_at}</span>
                  </div>
                </button>
              ))}
              {articles.length === 0 && (
                <div className="p-8 text-center text-xs text-slate-500 italic">
                  No articles generated yet. Launch your first research squad above!
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Right Column: Active Live Stepper OR Article Reader */}
        <div className="flex-1 min-w-0 flex flex-col gap-6">
          {activeRunId && (
            <LiveStepper
              runId={activeRunId}
              topic={activeTopic}
              onCancel={() => void handleCancelRun()}
              logs={runLogs}
              stage={runStage}
              traceUrl={activeTraceUrl}
            />
          )}

          {selectedArticle ? (
            <ArticleViewer
              topic={selectedArticle.topic}
              content={selectedArticle.content}
              wordCount={selectedArticle.word_count}
              generationTime={selectedArticle.generation_time_sec}
              onOpenCopilot={() => setIsCopilotOpen(true)}
            />
          ) : !activeRunId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 border border-slate-800/80 rounded-3xl bg-slate-900/30 text-center min-h-[450px]">
              <div className="p-4 bg-slate-800/50 rounded-2xl mb-4 text-indigo-400">
                <BookOpen className="w-8 h-8" aria-hidden="true" />
              </div>
              <h3 className="text-base font-bold text-slate-200 mb-1">No Article Selected</h3>
              <p className="text-xs text-slate-400 max-w-sm">
                Select an existing article from the library on the left, or launch a new multi-agent research run.
              </p>
            </div>
          ) : null}
        </div>
      </div>

      {/* 3. Copilot Drawer */}
      {selectedArticle && (
        <CopilotDrawer
          isOpen={isCopilotOpen}
          onClose={() => setIsCopilotOpen(false)}
          articleId={selectedArticle.id}
          onArticleRestored={() => void loadArticleDetail(selectedArticle.id)}
          onArticleUpdated={() => void loadArticleDetail(selectedArticle.id)}
        />
      )}

      {/* 4. Passwordless Auth Modal */}
      <AuthDialog
        isOpen={isAuthOpen}
        onSuccess={(authenticatedUser) => {
          setUser(authenticatedUser);
          setIsAuthOpen(false);
          void loadArticles();
          void loadTelemetry();
          void restoreActiveRun();
        }}
        onClose={() => setIsAuthOpen(false)}
      />

      {/* 5. API Keys Configuration Modal */}
      <ApiKeysDialog
        isOpen={isApiKeysOpen}
        onClose={() => setIsApiKeysOpen(false)}
      />
    </div>
  );
}
