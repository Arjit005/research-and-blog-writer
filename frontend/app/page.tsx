"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { SettingsModal } from "@/components/settings-modal";
import { QualityAuditorDrawer } from "@/components/quality-auditor-drawer";
import { VisualLibraryGallery } from "@/components/visual-library-gallery";
import { ImageLightboxViewer } from "@/components/image-lightbox-viewer";
import { VisualEvidenceDrawer } from "@/components/visual-evidence-drawer";
import { PremiumHero } from "@/components/premium-hero";
import { PremiumCard } from "@/components/premium-card";
import { PremiumButton } from "@/components/premium-button";
import { AmbientWebGLBackdrop } from "@/components/ambient-webgl-bg";
import { LandingPage } from "@/components/landing-page";
import { ResearchVisual } from "@/lib/api";
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
  Volume2,
  VolumeX,
  Settings,
  MoreHorizontal,
} from "lucide-react";

function cleanArticleForDisplay(content: string): string {
  const internal = /(?:Thought\s*:|I will now (?:provide|output|return)|I am going to (?:provide|output|return)|The complete (?:Markdown|finalized) (?:text|answer))/i.exec(content);
  let clean = content;
  if (internal) {
    const tail = content.slice(internal.index + internal[0].length);
    const title = /#{1,3}\s+[^#\n][^\n]*/.exec(tail);
    clean = title ? tail.slice(title.index) : content.slice(0, internal.index);
  }
  return clean
    .replace(/\n?\s*(?:Thought\s*:|Action\s*:|Action Input\s*:|Observation\s*:|I will now (?:provide|output|return)|The complete (?:Markdown|finalized) (?:text|answer))\b[\s\S]*$/i, "")
    .trim();
}

const ACTIVE_RUN_STORAGE_KEY = "research-studio:active-run";

interface StoredRun {
  runId: string;
  topic: string;
}

function playChimeSound() {
  try {
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.15); // A5
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.5);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.5);
  } catch {
    // AudioContext blocked by user policy
  }
}

function sendBrowserNotification(title: string, body: string) {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission === "granted") {
    new Notification(title, {
      body,
      icon: "/favicon.ico",
    });
  } else if (Notification.permission !== "denied") {
    void Notification.requestPermission().then((permission) => {
      if (permission === "granted") {
        new Notification(title, {
          body,
          icon: "/favicon.ico",
        });
      }
    });
  }
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
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isQualityAuditorOpen, setIsQualityAuditorOpen] = useState(false);
  const [activeCenterTab, setActiveCenterTab] = useState<"reader" | "visuals">("reader");
  const [visualsList, setVisualsList] = useState<ResearchVisual[]>([]);
  const [selectedVisualIndex, setSelectedVisualIndex] = useState<number | null>(null);
  const [evidenceDrawerVisual, setEvidenceDrawerVisual] = useState<ResearchVisual | null>(null);
  const [theme, setTheme] = useState<"light" | "dark">("dark");
  const [isSoundMuted, setIsSoundMuted] = useState(false);

  const toggleSoundMute = () => {
    const next = !isSoundMuted;
    setIsSoundMuted(next);
    try {
      localStorage.setItem("research-studio:sound-muted", String(next));
    } catch {}
  };

  useEffect(() => {
    try {
      const saved = localStorage.getItem("theme");
      const initialTheme = saved === "light" ? "light" : "dark";
      setTheme(initialTheme);
      document.documentElement.setAttribute("data-theme", initialTheme);
      document.documentElement.classList.toggle("dark", initialTheme === "dark");
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
  // Keep the article as the primary workspace; the squad panel is one click away.
  const [isRightCollapsed, setIsRightCollapsed] = useState(true);
  const [mobileDrawer, setMobileDrawer] = useState<"none" | "left" | "right">("none");
  const [isHeaderMenuOpen, setIsHeaderMenuOpen] = useState(false);
  const headerActionsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mobileDrawer === "none") return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    const background = [document.querySelector("header"), document.querySelector("main")].filter(Boolean) as HTMLElement[];
    const previousInert = background.map((element) => element.inert);
    background.forEach((element) => { element.inert = true; });
    document.body.style.overflow = "hidden";
    const dialog = document.querySelector<HTMLElement>('[role="dialog"][aria-modal="true"]');
    const focusable = () => dialog?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])');
    const frame = requestAnimationFrame(() => focusable()?.item(0)?.focus());
    const handleKeys = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMobileDrawer("none"); return; }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items?.length) return;
      const first = items.item(0);
      const last = items.item(items.length - 1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", handleKeys);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", handleKeys);
      background.forEach((element, index) => { element.inert = previousInert[index]; });
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [mobileDrawer]);

  useEffect(() => {
    if (!isHeaderMenuOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!headerActionsRef.current?.contains(event.target as Node)) setIsHeaderMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsHeaderMenuOpen(false);
        headerActionsRef.current?.querySelector<HTMLButtonElement>("[data-header-menu-trigger]")?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [isHeaderMenuOpen]);
  const workspaceGridColumns = isLeftCollapsed
    ? isRightCollapsed
      ? "lg:grid-cols-[3.5rem_minmax(0,1fr)] xl:grid-cols-[3.5rem_minmax(0,1fr)_3.5rem]"
      : "lg:grid-cols-[3.5rem_minmax(0,1fr)] xl:grid-cols-[3.5rem_minmax(0,1fr)_20rem]"
    : isRightCollapsed
      ? "lg:grid-cols-[20rem_minmax(0,1fr)] xl:grid-cols-[23rem_minmax(0,1fr)_3.5rem]"
      : "lg:grid-cols-[20rem_minmax(0,1fr)] xl:grid-cols-[23rem_minmax(0,1fr)_20rem]";

  // Copilot Drawer
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);

  const visibleArticle = useMemo(() => {
    if (!selectedArticle) return selectedArticle;
    const content = cleanArticleForDisplay(selectedArticle.content);
    return content === selectedArticle.content ? selectedArticle : { ...selectedArticle, content };
  }, [selectedArticle]);

  const hasVisibleArticle = Boolean(visibleArticle);

  const visibleStreamingDraft = useMemo(
    () => cleanArticleForDisplay(streamingDraft),
    [streamingDraft]
  );

  // System status
  const [systemStats, setSystemStats] = useState<TelemetryStats | null>(null);

  const sseClientRef = useRef<ResumableSSEClient | null>(null);
  const activeRunIdRef = useRef<string | null>(null);
  const activeTopicRef = useRef<string>("");
  const selectedArticleRef = useRef<ArticleDetail | null>(null);

  useEffect(() => {
    activeTopicRef.current = activeTopic;
  }, [activeTopic]);

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

  const loadVisuals = useCallback(async (articleId?: number) => {
    try {
      const res = await api.listVisuals({ article_id: articleId, limit: 100 });
      setVisualsList(res.items || []);
    } catch (err) {
      console.error("Failed to fetch research visuals:", err);
    }
  }, []);

  const loadArticleDetail = useCallback(async (id: number) => {
    try {
      const article = await api.getArticle(id);
      setSelectedArticle(article);
      void loadVisuals(id);
    } catch (err) {
      console.error("Failed to fetch article detail:", err);
    }
  }, [loadVisuals]);

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

      // Trigger browser notification and gentle completion chime
      if (!isSoundMuted) {
        playChimeSound();
      }
      sendBrowserNotification(
        "Research Complete! 🎉",
        `Your research blog post for "${activeTopicRef.current || "topic"}" is ready to view.`
      );
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
          } else if (event.type === "retry") {
            setRunLogs((prev) => [
              ...prev,
              {
                type: "status",
                detail: asString(event.data.message) || "Worker restarted; the run is queued for recovery.",
                timestamp: asNumber(event.data.timestamp) ?? Date.now() / 1000,
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
      // Request browser notification permission early on user interaction
      if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
        void Notification.requestPermission();
      }

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

  const [enteredWorkspace, setEnteredWorkspace] = useState(false);
  const databaseBackend = systemStats?.database.backend;

  if (!user && !enteredWorkspace) {
    return (
      <>
        <LandingPage
          onOpenAuth={() => setIsAuthOpen(true)}
          onEnterGuest={() => setEnteredWorkspace(true)}
        />
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
      </>
    );
  }

  return (
    <div className="research-studio-scene min-h-screen overflow-x-hidden bg-background text-foreground flex flex-col font-sans selection:bg-accent/20">
      {/* 1. SaaS Enterprise Header */}
      <header className="sticky top-0 z-40 w-full min-w-0 border-b border-border bg-surface/90 backdrop-blur-md px-3 sm:px-6 py-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
          {/* Mobile drawer toggle buttons */}
          <button
            type="button"
            onClick={() => setMobileDrawer(mobileDrawer === "left" ? "none" : "left")}
            className="lg:hidden p-2 bg-surface-raised border border-border text-foreground rounded-xl shrink-0"
            title="Toggle Research Library"
            aria-label="Toggle Research Library"
            aria-expanded={mobileDrawer === "left"}
          >
            <Menu className="w-4 h-4" />
          </button>

          <div className="brand-depth-mark" aria-hidden="true">
            <span className="brand-sheet brand-sheet-back" />
            <span className="brand-sheet brand-sheet-front" />
          </div>
          <div>
            <h1 className="text-sm md:text-base font-bold tracking-tight text-foreground flex items-center gap-2 whitespace-nowrap">
              Research Studio
              <span className="hidden md:inline px-2 py-0.5 text-[10px] uppercase font-mono font-bold bg-accent-soft text-accent border border-accent/25 rounded-md">
                Workspace
              </span>
            </h1>
            <p className="text-[11px] text-muted-foreground hidden sm:block">
              Autonomous 4-Agent Research Squad &amp; Mermaid Visual Canvas
            </p>
          </div>
        </div>

        {/* System telemetry & Auth badges */}
        <div ref={headerActionsRef} className="workspace-header-actions relative flex shrink-0 items-center gap-1 sm:gap-3">
          {systemStats && (
            <div className="hidden xl:flex items-center gap-2 px-3 py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground">
              <Database className="w-3.5 h-3.5 text-accent" aria-hidden="true" />
              <span>{databaseBackend ? databaseBackend.toUpperCase() : "DB"}</span>
              <span className="text-muted-foreground">|</span>
              <span className="text-muted-foreground">
                Cache hits: {systemStats.cache.metrics.total_hits ?? 0}
              </span>
            </div>
          )}

          {/* Sound Mute Toggle */}
          <button
            type="button"
            onClick={toggleSoundMute}
            className="optional-header-action hidden sm:flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground transition"
            title={isSoundMuted ? "Unmute completion sound" : "Mute completion sound"}
            aria-label="Toggle Sound"
          >
            {isSoundMuted ? (
              <VolumeX className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <Volume2 className="w-3.5 h-3.5 text-accent" />
            )}
            <span className="hidden sm:inline">{isSoundMuted ? "Muted" : "Sound"}</span>
          </button>

          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={toggleTheme}
            className="optional-header-action flex items-center gap-1 sm:gap-1.5 p-2 sm:px-3 sm:py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground transition"
            title={theme === "light" ? "Switch to Dark Mode" : "Switch to Light Mode"}
            aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}
          >
            {theme === "light" ? (
              <Moon className="w-3.5 h-3.5 text-muted-foreground" />
            ) : (
              <Sun className="w-3.5 h-3.5 text-amber-400" />
            )}
            <span className="hidden sm:inline capitalize">{theme === "light" ? "Dark" : "Light"}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsApiKeysOpen(true)}
            className="optional-header-action flex items-center gap-1 sm:gap-1.5 p-2 sm:px-3 sm:py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground transition"
            title="Configure API Keys (Gemini / OpenRouter)"
            aria-label="Configure API keys"
          >
            <Key className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" aria-hidden="true" />
            <span className="hidden sm:inline">API Keys</span>
          </button>

          {/* Settings Button */}
          <button
            type="button"
            onClick={() => setIsSettingsOpen(true)}
            className="optional-header-action flex items-center gap-1 sm:gap-1.5 p-2 sm:px-3 sm:py-1.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground transition"
            title="Workspace Settings"
            aria-label="Settings"
          >
            <Settings className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="hidden sm:inline">Settings</span>
          </button>

          {/* Mobile Right drawer toggle */}
          <button
            type="button"
            onClick={() => setMobileDrawer(mobileDrawer === "right" ? "none" : "right")}
            className="optional-header-action hidden sm:block lg:hidden p-2 bg-surface-raised border border-border text-foreground rounded-xl relative"
            title="Toggle AI Command Center"
            aria-label="Toggle AI Command Center"
            aria-expanded={mobileDrawer === "right"}
          >
            <Cpu className="w-4 h-4 text-accent" />
            {activeRunId && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
            )}
          </button>

          <button
            type="button"
            data-header-menu-trigger
            onClick={() => setIsHeaderMenuOpen((open) => !open)}
            className="sm:hidden p-2 bg-surface-raised border border-border text-foreground rounded-xl"
            aria-label="More workspace actions"
            aria-expanded={isHeaderMenuOpen}
            aria-controls="mobile-header-actions"
          >
            <MoreHorizontal className="w-4 h-4" aria-hidden="true" />
          </button>
          {isHeaderMenuOpen && (
            <div id="mobile-header-actions" className="sm:hidden absolute right-0 top-full mt-2 z-50 w-56 rounded-2xl border border-border bg-surface p-2 shadow-2xl" aria-label="Workspace actions">
              <button type="button" onClick={() => { toggleTheme(); setIsHeaderMenuOpen(false); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground hover:bg-surface-raised">
                {theme === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />} Toggle appearance
              </button>
              <button type="button" onClick={() => { setIsApiKeysOpen(true); setIsHeaderMenuOpen(false); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground hover:bg-surface-raised"><Key className="h-4 w-4" /> API keys</button>
              <button type="button" onClick={() => { setIsSettingsOpen(true); setIsHeaderMenuOpen(false); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground hover:bg-surface-raised"><Settings className="h-4 w-4" /> Settings</button>
              <button type="button" onClick={() => { setMobileDrawer("right"); setIsHeaderMenuOpen(false); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground hover:bg-surface-raised"><Cpu className="h-4 w-4" /> Command center</button>
              <button type="button" onClick={() => { toggleSoundMute(); setIsHeaderMenuOpen(false); }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-foreground hover:bg-surface-raised">{isSoundMuted ? <VolumeX className="h-4 w-4" /> : <Volume2 className="h-4 w-4" />} {isSoundMuted ? "Enable sound" : "Mute sound"}</button>
            </div>
          )}

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
              className="px-4 py-1.5 bg-accent text-accent-foreground rounded-xl text-xs font-semibold transition shadow-md shadow-accent/20"
            >
              Sign In
            </button>
          )}
        </div>
      </header>

      {/* 2. Responsive 3-Panel Workspace */}
      <main className={`flex-1 grid w-full max-w-[1920px] mx-auto grid-cols-1 ${workspaceGridColumns} p-3 sm:p-5 md:p-6 gap-4 lg:gap-5 min-h-0 lg:h-[calc(100vh-4.25rem)] lg:overflow-hidden`}>
        {/* Panel A: Left Sidebar (Desktop) */}
        <div className={`hidden lg:flex min-w-0 min-h-0 ${isLeftCollapsed ? "w-14" : ""}`}>
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
            onOpenVisualLibrary={() => {
              void loadVisuals(selectedArticle?.id);
              setActiveCenterTab("visuals");
            }}
            isCollapsed={isLeftCollapsed}
            onToggleCollapse={() => setIsLeftCollapsed(!isLeftCollapsed)}
          />
        </div>

        {/* Panel B: Center Professional Article Editor & Workspace */}
        <div className="min-w-0 min-h-0 flex flex-col gap-4 overflow-y-auto pr-1">
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

          {/* Center Tabs: Research Report vs Visual Library */}
          <div className="flex items-center justify-between border-b border-border pb-2.5">
            <div
              role="tablist"
              aria-label="Research workspace view"
              onKeyDown={(event) => {
                if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                event.preventDefault();
                const nextTab = event.key === "ArrowRight" ? "visuals" : "reader";
                setActiveCenterTab(nextTab);
                if (nextTab === "visuals") void loadVisuals(selectedArticle?.id);
                event.currentTarget.querySelector<HTMLElement>(`#research-${nextTab}-tab`)?.focus();
              }}
              className="flex items-center gap-2"
            >
              <button
                type="button"
                onClick={() => setActiveCenterTab("reader")}
                role="tab"
                id="research-reader-tab"
                aria-controls="research-workspace-panel"
                aria-selected={activeCenterTab === "reader"}
                tabIndex={activeCenterTab === "reader" ? 0 : -1}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer flex items-center gap-2 ${
                  activeCenterTab === "reader"
                    ? "bg-accent text-accent-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
                }`}
              >
                <BookOpen className="w-3.5 h-3.5" />
                <span>Research Article</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  void loadVisuals(selectedArticle?.id);
                  setActiveCenterTab("visuals");
                }}
                role="tab"
                id="research-visuals-tab"
                aria-controls="research-workspace-panel"
                aria-selected={activeCenterTab === "visuals"}
                tabIndex={activeCenterTab === "visuals" ? 0 : -1}
                className={`px-3.5 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer flex items-center gap-2 ${
                  activeCenterTab === "visuals"
                    ? "bg-accent text-accent-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Visual Research System</span>
                {visualsList.length > 0 && (
                  <span
                    className={`px-1.5 py-0.5 text-[10px] rounded-full font-mono ${
                      activeCenterTab === "visuals"
                        ? "bg-accent-foreground/15 text-accent-foreground"
                        : "bg-accent-soft text-accent"
                    }`}
                  >
                    {visualsList.length}
                  </span>
                )}
              </button>
            </div>
          </div>

          <div role="tabpanel" id="research-workspace-panel" aria-labelledby={activeCenterTab === "visuals" ? "research-visuals-tab" : "research-reader-tab"} tabIndex={0} className="min-h-0 flex-1">
          {activeCenterTab === "visuals" ? (
            <div className="space-y-6">
              <div className="p-4 bg-surface border border-border rounded-2xl flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-foreground">Visual Research Library</h3>
                  <p className="text-xs text-muted-foreground">
                    Traceable figures, Mermaid architectural blueprints, and interactive empirical charts.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveCenterTab("reader")}
                  className="px-3 py-1.5 bg-surface-raised border border-border text-foreground hover:bg-surface text-xs font-medium rounded-xl transition cursor-pointer"
                >
                  Return to Report
                </button>
              </div>

              <VisualLibraryGallery
                visuals={visualsList}
                onSelectVisual={(idx) => setSelectedVisualIndex(idx)}
                onDeleteVisual={async (id) => {
                  try {
                    await api.deleteVisual(id);
                    await loadVisuals(selectedArticle?.id);
                  } catch (e) {
                    console.error("Failed to delete visual:", e);
                  }
                }}
                onOpenEvidence={(v) => setEvidenceDrawerVisual(v)}
              />
            </div>
          ) : hasVisibleArticle && visibleArticle ? (
            <ArticleViewer
              topic={visibleArticle.topic}
              content={visibleArticle.content}
              articleId={visibleArticle.id}
              wordCount={visibleArticle.word_count}
              generationTime={visibleArticle.generation_time_sec}
              onOpenCopilot={() => setIsCopilotOpen(true)}
              onOpenVersionHistory={() => setIsCopilotOpen(true)}
              onOpenQualityAuditor={() => setIsQualityAuditorOpen(true)}
              onOpenVisualLibrary={() => {
                void loadVisuals(visibleArticle.id);
                setActiveCenterTab("visuals");
              }}
            />
          ) : activeRunId && visibleStreamingDraft.trim() ? (
            <ArticleViewer
              topic={activeTopic}
              content={visibleStreamingDraft}
              isStreaming={true}
            />
          ) : activeRunId ? (
            <div className="flex-1 flex flex-col items-center justify-center p-12 border border-border/80 rounded-3xl bg-surface/30 text-center min-h-[480px]">
              <div className="p-4 bg-signal/10 border border-signal/20 rounded-2xl mb-4 text-signal animate-pulse">
                <Cpu className="w-8 h-8" />
              </div>
              <h3 className="text-base font-bold text-foreground mb-1">
                AI Squad Pipeline in Progress
              </h3>
              <p className="text-xs text-muted-foreground max-w-md mb-5">
                Researching <strong className="text-foreground">&ldquo;{activeTopic}&rdquo;</strong>. Watch real-time
                agent telemetry and diagram synthesis in the Command Center.
              </p>

              {/* Dynamic Stage Progress Bar */}
              <div className="w-full max-w-xs mb-4">
                <div className="flex justify-between text-[11px] font-medium text-foreground mb-1.5">
                  <span>{runStage === 1 ? "Researching sources" : runStage === 2 ? "Analysis and drafting" : runStage === 3 ? "Integrating research" : "Final editorial review"}</span>
                  <span className="font-mono text-signal font-bold">Stage {Math.min(runStage, 4)} of 4</span>
                </div>
                <div role="progressbar" aria-label="Research pipeline stage" aria-valuemin={1} aria-valuemax={4} aria-valuenow={Math.min(runStage, 4)} className="w-full h-2 bg-surface-raised rounded-full overflow-hidden border border-border/50">
                  <div
                    className="h-full bg-gradient-to-r from-accent via-signal to-purple-500 rounded-full transition-all duration-700 ease-out"
                    style={{ width: `${Math.min(runStage, 4) * 25}%` }}
                  />
                </div>
              </div>

              <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                <span>Stage {runStage}/4 Active</span>
                <span>&bull;</span>
                <span>{runLogs.length} events logged</span>
              </div>
            </div>
          ) : (
            <>
              <AmbientWebGLBackdrop />
              <PremiumCard tilt hover={false} bordered className="relative z-10 flex-1 flex flex-col items-center justify-center min-h-[460px] bg-surface/85 backdrop-blur-md">
              <div className="w-full max-w-xl flex flex-col items-center">
                <PremiumHero className="w-full mb-8" />
                <span className="mb-3 inline-flex items-center gap-2 rounded-full border border-accent/25 bg-accent-soft px-3 py-1 text-[10px] font-mono font-semibold uppercase tracking-[0.2em] text-accent">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_10px_#34d399]" />
                  Four agents · one research desk
                </span>
                <h3 className="text-2xl sm:text-3xl font-semibold tracking-tight text-foreground mb-2">
                  Begin with a question.
                </h3>
                <p className="text-base text-foreground/90 leading-relaxed max-w-md mb-6 text-center">
                  Follow a technical idea from source discovery through a clear, illustrated research brief.
                </p>
                <form
                  onSubmit={handleStartRun}
                  className="w-full max-w-lg flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5"
                >
                  <input
                    type="text"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                    placeholder="e.g. Distributed Consensus in TiDB..."
                    aria-label="Research topic"
                    className="flex-1 px-4 py-2.5 bg-background border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-accent/45 focus:border-accent transition"
                  />
                  <PremiumButton
                    type="submit"
                    disabled={isSubmitting || Boolean(activeRunId) || !topic.trim()}
                    variant="accent"
                    size="lg"
                  >
                    {isSubmitting ? "Starting…" : "Start research"}
                  </PremiumButton>
                </form>
                <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                  {[
                    "Distributed Consensus in TiDB",
                    "Zero-Knowledge Proofs in Cloud Security",
                    "Rust vs Go Event-Driven Microservices",
                  ].map((prompt) => (
                    <PremiumButton
                      key={prompt}
                      type="button"
                      onClick={() => setTopic(prompt)}
                      variant="ghost"
                      size="sm"
                    >
                      {prompt}
                    </PremiumButton>
                  ))}
                </div>
              </div>
            </PremiumCard>
            </>
          )}
          </div>
        </div>

        {/* Panel C: Right AI Command Center (Desktop) */}
        <div className={`hidden xl:flex min-w-0 min-h-0 ${isRightCollapsed ? "w-14" : ""}`}>
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
        <div className="lg:hidden fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex">
          <button type="button" aria-label="Close workspace library" onClick={() => setMobileDrawer("none")} className="absolute inset-0 h-full w-full cursor-default" />
          <section role="dialog" aria-modal="true" aria-label="Workspace Library" className="relative z-10 w-full max-w-xs bg-surface text-foreground p-4 border-r border-border overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <span className="text-xs font-bold uppercase text-foreground">Workspace Library</span>
              <button
                type="button"
                onClick={() => setMobileDrawer("none")}
                aria-label="Close workspace library"
                className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg bg-surface-raised cursor-pointer"
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
              onOpenVisualLibrary={() => {
                void loadVisuals(selectedArticle?.id);
                setActiveCenterTab("visuals");
                setMobileDrawer("none");
              }}
              isCollapsed={false}
              onToggleCollapse={() => setMobileDrawer("none")}
            />
          </section>
        </div>
      )}

      {mobileDrawer === "right" && (
        <div className="lg:hidden fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex justify-end">
          <button type="button" aria-label="Close command center" onClick={() => setMobileDrawer("none")} className="absolute inset-0 h-full w-full cursor-default" />
          <section role="dialog" aria-modal="true" aria-label="Command Center" className="relative z-10 w-full max-w-sm bg-surface text-foreground p-4 border-l border-border overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <span className="text-xs font-bold uppercase text-foreground">Command Center</span>
              <button
                type="button"
                onClick={() => setMobileDrawer("none")}
                aria-label="Close command center"
                className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg bg-surface-raised cursor-pointer"
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
          </section>
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

      {/* 7. Enterprise Workspace Settings Modal */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        userEmail={user?.email}
        theme={theme}
        onThemeChange={(t) => {
          setTheme(t);
          try {
            localStorage.setItem("theme", t);
            document.documentElement.setAttribute("data-theme", t);
            document.documentElement.classList.toggle("dark", t === "dark");
          } catch {}
        }}
        isSoundMuted={isSoundMuted}
        onSoundMuteToggle={toggleSoundMute}
      />
      {/* 8. Research Quality Auditor Drawer (Section 8) */}
      {selectedArticle && (
        <QualityAuditorDrawer
          isOpen={isQualityAuditorOpen}
          onClose={() => setIsQualityAuditorOpen(false)}
          articleId={selectedArticle.id}
        />
      )}

      {/* 9. Visual Lightbox Viewer (Modules B & C) */}
      {selectedVisualIndex !== null && (
        <ImageLightboxViewer
          visuals={visualsList}
          currentIndex={selectedVisualIndex}
          isOpen={selectedVisualIndex !== null}
          onClose={() => setSelectedVisualIndex(null)}
          onIndexChange={(idx) => setSelectedVisualIndex(idx)}
          onOpenEvidence={(v) => {
            setSelectedVisualIndex(null);
            setEvidenceDrawerVisual(v);
          }}
        />
      )}

      {/* 10. Visual Evidence & Traceability Drawer (Module F) */}
      {evidenceDrawerVisual && (
        <VisualEvidenceDrawer
          isOpen={evidenceDrawerVisual !== null}
          onClose={() => setEvidenceDrawerVisual(null)}
          visual={evidenceDrawerVisual}
        />
      )}
    </div>
  );
}
