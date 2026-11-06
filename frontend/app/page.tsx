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
import { ArticleViewer } from "@/components/article-viewer";
import { LeftSidebar } from "@/components/left-sidebar";
import { AICommandCenter, SquadLog } from "@/components/ai-command-center";
import { CopilotDrawer } from "@/components/copilot-drawer";
import { ApiKeysDialog } from "@/components/api-keys-dialog";
import {
  Sparkles,
  BookOpen,
  Database,
  LogOut,
  UserCheck,
  Key,
  Menu,
  Cpu,
  Sun,
  Moon,
} from "lucide-react";

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

  // Active run state
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [activeTopic, setActiveTopic] = useState("");
  const [streamingDraft, setStreamingDraft] = useState<string>("");
  const [runLogs, setRunLogs] = useState<SquadLog[]>([]);
  const [runStage, setRunStage] = useState(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [activeTraceUrl, setActiveTraceUrl] = useState<string | null>(null);
  const [isApiKeysOpen, setIsApiKeysOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    try {
      const saved = localStorage.getItem("theme");
      if (saved === "dark") {
        setTheme("dark");
      } else {
        setTheme("light");
      }
    } catch {}
  }, []);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    try {
      localStorage.setItem("theme", next);
      if (next === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.setAttribute("data-theme", "light");
        document.documentElement.classList.remove("dark");
      }
    } catch {}
  };

  // Responsive Drawer & Panels
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightCollapsed, setIsRightCollapsed] = useState(false);
  const [mobileDrawer, setMobileDrawer] = useState<"none" | "left" | "right">("none");

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
      setStreamingDraft("");
      clearStoredRun();
      closeStream();

      await loadArticles();
      if (articleId) {
        await loadArticleDetail(articleId);
      }
    },
    [closeStream, loadArticles, loadArticleDetail]
  );

  const handleDeleteArticle = useCallback(
    async (id: number) => {
      if (!window.confirm("Are you sure you want to delete this article? This will free up database space.")) {
        return;
      }
      try {
        await api.deleteArticle(id);
        if (selectedArticle?.id === id) {
          setSelectedArticle(null);
        }
        await loadArticles();
      } catch (err) {
        alert(errorMessage(err, "Failed to delete article."));
      }
    },
    [selectedArticle, loadArticles]
  );

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

        setRunError(
          `${error.message} The server still reports this run as "${status.status}".`
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
      setStreamingDraft("");
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
              {
                type: "step",
                detail: asString(event.data.detail),
                agent: event.data.agent ? asString(event.data.agent) : undefined,
                timestamp: asNumber(event.data.timestamp),
              },
            ]);
          } else if (event.type === "token") {
            const delta = asString(event.data.delta);
            if (delta) {
              setStreamingDraft((prev) => prev + delta);
            }
          } else if (event.type === "task_done") {
            const completedStage = asNumber(event.data.completed_stage) ?? 0;
            if (completedStage === 1) {
              // Lead Researcher done -> Stage 2 (Parallel Writer & Diagram Architect)
              setRunStage(2);
            } else if (completedStage === 2) {
              // First parallel agent done -> Still in Stage 2 (awaiting partner)
              setRunStage(2);
            } else if (completedStage === 3) {
              // BOTH parallel agents completed -> Advance to Stage 4 (Editorial Director)
              setRunStage(4);
            } else if (completedStage >= 4) {
              setRunStage(4);
            } else {
              setRunStage((current) => Math.min(current + 1, 4));
            }
            const agentName = event.data.agent ? asString(event.data.agent) : "";
            const msg = event.data.message ? asString(event.data.message) : "Stage finished";
            const dur = event.data.duration_sec ? (" (" + event.data.duration_sec + "s)") : "";
            setRunLogs((prev) => [
              ...prev,
              {
                type: "stage_complete",
                detail: msg + dur,
                agent: agentName || undefined,
                timestamp: asNumber(event.data.timestamp),
              },
            ]);
          } else if (event.type === "status") {
            setRunLogs((prev) => [
              ...prev,
              {
                type: "status",
                detail: asString(event.data.stage) || asString(event.data.status),
                timestamp: Date.now() / 1000,
              },
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
      console.error("Could not reattach to stored research run:", err);
      clearStoredRun();
    }
  }, [attachToRun, handleRunCompleted]);

  // Boot
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
    setRunError(null);
    try {
      const runRes = await api.createRun({
        topic: topic.trim(),
        tone,
        audience,
        target_length: targetLength,
      });
      attachToRun(runRes.run_id, runRes.topic);
      // Close mobile drawer on start
      setMobileDrawer("none");
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
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans selection:bg-blue-500/20">
      {/* 1. SaaS Enterprise Header */}
      <header className="sticky top-0 z-40 w-full border-b border-border bg-surface/90 backdrop-blur-md px-4 sm:px-6 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Mobile drawer toggle buttons */}
          <button
            type="button"
            onClick={() => setMobileDrawer(mobileDrawer === "left" ? "none" : "left")}
            className="lg:hidden p-2 bg-surface-raised border border-border text-foreground rounded-xl"
            title="Toggle Research Library"
          >
            <Menu className="w-4 h-4" />
          </button>

          <div className="p-2 bg-gradient-to-tr from-blue-600 to-indigo-600 rounded-xl shadow-lg shadow-blue-500/20">
            <Sparkles className="w-5 h-5 text-white" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-sm md:text-base font-bold tracking-tight text-foreground flex items-center gap-2">
              Research Studio
              <span className="px-2 py-0.5 text-[10px] uppercase font-mono font-bold bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20 rounded-md">
                Workspace
              </span>
            </h1>
            <p className="text-[11px] text-muted-foreground hidden sm:block">
              Autonomous 4-Agent Research Squad & Mermaid Visual Canvas
            </p>
          </div>
        </div>

        {/* System telemetry & Auth badges */}
        <div className="flex items-center gap-2 sm:gap-3">
          {systemStats && (
            <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground">
              <Database className="w-3.5 h-3.5 text-blue-500" aria-hidden="true" />
              <span>{databaseBackend ? databaseBackend.toUpperCase() : "DB"}</span>
              <span className="text-muted-foreground">|</span>
              <span className="text-muted-foreground">
                Cache hits: {systemStats.cache.metrics.total_hits ?? 0}
              </span>
            </div>
          )}

          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={toggleTheme}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border rounded-xl text-xs text-foreground transition"
            title={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
            aria-label="Toggle Theme"
          >
            {theme === "light" ? (
              <Moon className="w-3.5 h-3.5 text-slate-700" />
            ) : (
              <Sun className="w-3.5 h-3.5 text-amber-400" />
            )}
            <span className="hidden sm:inline capitalize">{theme === "light" ? "Dark" : "Light"}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsApiKeysOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border rounded-xl text-xs text-foreground transition"
            title="Configure API Keys (Gemini / OpenRouter)"
          >
            <Key className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" aria-hidden="true" />
            <span className="hidden sm:inline">API Keys</span>
          </button>

          {/* Mobile Right drawer toggle */}
          <button
            type="button"
            onClick={() => setMobileDrawer(mobileDrawer === "right" ? "none" : "right")}
            className="lg:hidden p-2 bg-surface-raised border border-border text-foreground rounded-xl relative"
            title="Toggle AI Command Center"
          >
            <Cpu className="w-4 h-4 text-blue-500" />
            {activeRunId && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            )}
          </button>

          {user ? (
            <div className="flex items-center gap-2 pl-1 sm:pl-2">
              <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-surface-raised border border-border rounded-xl text-xs">
                <UserCheck className="w-3.5 h-3.5 text-emerald-500" aria-hidden="true" />
                <span className="text-foreground font-medium truncate max-w-[140px] md:max-w-none">
                  {user.email}
                </span>
              </div>
              <button
                type="button"
                onClick={() => void handleLogout()}
                title="Log out"
                aria-label="Log out"
                className="p-2 hover:bg-surface-raised text-muted-foreground hover:text-foreground rounded-xl transition"
              >
                <LogOut className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setIsAuthOpen(true)}
              className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-semibold transition shadow-md shadow-blue-600/20"
            >
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* 2. Responsive 3-Panel Workspace */}
      <main className="flex-1 flex w-full max-w-[1920px] mx-auto p-3 sm:p-5 md:p-6 gap-6 overflow-hidden">
        {/* Panel A: Left Sidebar (Desktop) */}
        <div className="hidden lg:flex shrink-0">
          <LeftSidebar
            topic={topic}
            setTopic={setTopic}
            tone={tone}
            setTone={setTone}
            audience={audience}
            setAudience={setAudience}
            targetLength={targetLength}
            setTargetLength={setTargetLength}
            isSubmitting={isSubmitting}
            activeRunId={activeRunId}
            onSubmit={handleStartRun}
            articles={articles}
            selectedArticleId={selectedArticle?.id ?? null}
            onSelectArticle={(id) => void loadArticleDetail(id)}
            onDeleteArticle={handleDeleteArticle}
            isCollapsed={isLeftCollapsed}
            onToggleCollapse={() => setIsLeftCollapsed(!isLeftCollapsed)}
          />
        </div>

        {/* Panel B: Center Professional Article Editor & Workspace */}
        <div className="flex-1 min-w-0 flex flex-col gap-6 overflow-y-auto pr-1">
          {runError && (
            <div
              role="alert"
              className="p-3.5 bg-red-500/10 border border-red-500/30 rounded-2xl text-xs text-red-400 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-lg"
            >
              <div>{runError}</div>
              {(runError.includes("429") ||
                runError.toLowerCase().includes("rate limit") ||
                runError.includes("free-models-per-day")) && (
                <button
                  type="button"
                  onClick={() => setIsApiKeysOpen(true)}
                  className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 font-medium rounded-xl text-xs transition"
                >
                  Configure Free Gemini Key (1,500 req/day)
                </button>
              )}
            </div>
          )}

          {selectedArticle ? (
            <ArticleViewer
              topic={selectedArticle.topic}
              content={selectedArticle.content}
              wordCount={selectedArticle.word_count}
              generationTime={selectedArticle.generation_time_sec}
              onOpenCopilot={() => setIsCopilotOpen(true)}
              onOpenVersionHistory={() => setIsCopilotOpen(true)}
            />
          ) : activeRunId && streamingDraft.trim() ? (
            <ArticleViewer
              topic={activeTopic}
              content={streamingDraft}
              isStreaming={true}
            />
          ) : activeRunId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 border border-slate-800/80 rounded-3xl bg-slate-900/30 text-center min-h-[480px]">
              <div className="p-4 bg-indigo-500/10 border border-indigo-500/20 rounded-2xl mb-4 text-indigo-400 animate-pulse">
                <Cpu className="w-8 h-8" />
              </div>
              <h3 className="text-base font-bold text-slate-100 mb-1">
                AI Squad Pipeline in Progress
              </h3>
              <p className="text-xs text-slate-400 max-w-md mb-4">
                Researching <strong className="text-slate-200">&ldquo;{activeTopic}&rdquo;</strong>. Watch real-time
                agent telemetry and diagram synthesis in the Command Center.
              </p>
              <div className="flex items-center gap-2 text-xs font-mono text-slate-500">
                <span>Stage {runStage}/4 Active</span>
                <span>&bull;</span>
                <span>{runLogs.length} events logged</span>
              </div>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center p-12 border border-slate-800/80 rounded-3xl bg-slate-900/30 text-center min-h-[480px]">
              <div className="p-4 bg-slate-800/50 rounded-2xl mb-4 text-indigo-400">
                <BookOpen className="w-8 h-8" aria-hidden="true" />
              </div>
              <h3 className="text-base font-bold text-slate-200 mb-1">No Article Selected</h3>
              <p className="text-xs text-slate-400 max-w-sm mb-6">
                Select an existing article from the library, or launch a new multi-agent research run to
                generate a publication-ready blog post with Mermaid diagrams.
              </p>
              <button
                type="button"
                onClick={() => {
                  setTopic("Autonomous Multi-Agent AI Systems: 2026 Architecture");
                }}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-xl text-xs text-indigo-300 font-medium transition"
              >
                Load Suggested Topic
              </button>
            </div>
          )}
        </div>

        {/* Panel C: Right AI Command Center (Desktop) */}
        <div className="hidden lg:flex shrink-0">
          <AICommandCenter
            runId={activeRunId}
            topic={activeTopic}
            stage={runStage}
            logs={runLogs}
            onCancel={() => void handleCancelRun()}
            traceUrl={activeTraceUrl}
            isCollapsed={isRightCollapsed}
            onToggleCollapse={() => setIsRightCollapsed(!isRightCollapsed)}
            articleSummary={{
              wordCount: selectedArticle?.word_count,
              generationTime: selectedArticle?.generation_time_sec,
            }}
          />
        </div>
      </main>

      {/* 3. Mobile Drawers */}
      {mobileDrawer === "left" && (
        <div className="lg:hidden fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex">
          <div className="w-full max-w-xs bg-slate-900 p-4 border-r border-slate-800 overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <span className="text-xs font-bold uppercase text-slate-300">Workspace Library</span>
              <button
                type="button"
                onClick={() => setMobileDrawer("none")}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg bg-slate-800"
              >
                ✕
              </button>
            </div>
            <LeftSidebar
              topic={topic}
              setTopic={setTopic}
              tone={tone}
              setTone={setTone}
              audience={audience}
              setAudience={setAudience}
              targetLength={targetLength}
              setTargetLength={setTargetLength}
              isSubmitting={isSubmitting}
              activeRunId={activeRunId}
              onSubmit={handleStartRun}
              articles={articles}
              selectedArticleId={selectedArticle?.id ?? null}
              onSelectArticle={(id) => {
                void loadArticleDetail(id);
                setMobileDrawer("none");
              }}
              onDeleteArticle={handleDeleteArticle}
              isCollapsed={false}
              onToggleCollapse={() => setMobileDrawer("none")}
            />
          </div>
          <div className="flex-1" onClick={() => setMobileDrawer("none")} />
        </div>
      )}

      {mobileDrawer === "right" && (
        <div className="lg:hidden fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex justify-end">
          <div className="flex-1" onClick={() => setMobileDrawer("none")} />
          <div className="w-full max-w-sm bg-slate-900 p-4 border-l border-slate-800 overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <span className="text-xs font-bold uppercase text-slate-300">Command Center</span>
              <button
                type="button"
                onClick={() => setMobileDrawer("none")}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg bg-slate-800"
              >
                ✕
              </button>
            </div>
            <AICommandCenter
              runId={activeRunId}
              topic={activeTopic}
              stage={runStage}
              logs={runLogs}
              onCancel={() => void handleCancelRun()}
              traceUrl={activeTraceUrl}
              isCollapsed={false}
              onToggleCollapse={() => setMobileDrawer("none")}
              articleSummary={{
                wordCount: selectedArticle?.word_count,
                generationTime: selectedArticle?.generation_time_sec,
              }}
            />
          </div>
        </div>
      )}

      {/* 4. Copilot Drawer */}
      {selectedArticle && (
        <CopilotDrawer
          isOpen={isCopilotOpen}
          onClose={() => setIsCopilotOpen(false)}
          articleId={selectedArticle.id}
          onArticleRestored={() => void loadArticleDetail(selectedArticle.id)}
          onArticleUpdated={() => void loadArticleDetail(selectedArticle.id)}
        />
      )}

      {/* 5. Authentication Dialog (Protected & Unmodified) */}
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

      {/* 6. API Keys Configuration Modal */}
      <ApiKeysDialog
        isOpen={isApiKeysOpen}
        onClose={() => setIsApiKeysOpen(false)}
      />
    </div>
  );
}