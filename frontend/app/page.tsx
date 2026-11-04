"use client";

import React, { useState, useEffect, useRef } from "react";
import { api, User, ArticleSummary, ArticleDetail } from "@/lib/api";
import { ResumableSSEClient } from "@/lib/sse";
import { AuthDialog } from "@/components/auth-dialog";
import { LiveStepper } from "@/components/live-stepper";
import { ArticleViewer } from "@/components/article-viewer";
import { CopilotDrawer } from "@/components/copilot-drawer";
import {
  Sparkles,
  BookOpen,
  SlidersHorizontal,
  ChevronDown,
  Database,
  LogOut,
  UserCheck,
} from "lucide-react";

const PRESET_TOPICS = [
  "Autonomous Multi-Agent AI Systems: 2026 Architecture",
  "Quantum Computing Advancements in Post-RSA Cryptography",
  "High-Throughput Event-Driven Microservices in Rust & Go",
  "Zero-Knowledge Proofs in Enterprise Cloud Security",
];

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

  // Copilot Drawer
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);

  // System status
  const [systemStats, setSystemStats] = useState<any>(null);

  const sseClientRef = useRef<ResumableSSEClient | null>(null);

  // Check login on load
  useEffect(() => {
    api
      .getMe()
      .then((u) => {
        setUser(u);
        loadArticles();
        loadTelemetry();
      })
      .catch(() => {
        // Not logged in
        setIsAuthOpen(true);
      });

    return () => {
      if (sseClientRef.current) sseClientRef.current.close();
    };
  }, []);

  const loadArticles = async () => {
    try {
      const list = await api.listArticles();
      setArticles(list);
      if (list.length > 0 && !selectedArticle && !activeRunId) {
        loadArticleDetail(list[0].id);
      }
    } catch (err) {
      console.error("Failed to load articles:", err);
    }
  };

  const loadArticleDetail = async (id: number) => {
    try {
      const art = await api.getArticle(id);
      setSelectedArticle(art);
    } catch (err) {
      console.error("Failed to fetch article detail:", err);
    }
  };

  const loadTelemetry = async () => {
    try {
      const stats = await api.getTelemetryStats();
      setSystemStats(stats);
    } catch (err) {
      console.error("Failed to fetch telemetry:", err);
    }
  };

  const handleStartRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;

    if (!user) {
      setIsAuthOpen(true);
      return;
    }

    setRunError(null);
    setIsSubmitting(true);
    setRunLogs([]);
    setRunStage(1);
    setActiveTraceUrl(null);

    try {
      const runRes = await api.createRun({
        topic: topic.trim(),
        tone,
        audience,
        target_length: targetLength,
      });

      setActiveRunId(runRes.run_id);
      setActiveTopic(runRes.topic);
      setSelectedArticle(null);

      // Connect SSE stream
      const sse = new ResumableSSEClient(
        runRes.run_id,
        (ev) => {
          if (ev.type === "step") {
            setRunLogs((prev) => [...prev, { type: "step", detail: ev.data.detail, timestamp: ev.data.timestamp }]);
          } else if (ev.type === "task_done") {
            setRunStage((s) => Math.min(s + 1, 4));
            setRunLogs((prev) => [...prev, { type: "stage_complete", detail: `Stage finished`, timestamp: ev.data.timestamp }]);
          } else if (ev.type === "status") {
            setRunLogs((prev) => [...prev, { type: "status", detail: ev.data.stage, timestamp: Date.now() }]);
          }
        },
        (err) => {
          console.error("Run error event:", err);
          setRunError(err.message || "Pipeline execution failed.");
          setActiveRunId(null);
        },
        async (completedData) => {
          setRunStage(4);
          if (completedData.trace_url) setActiveTraceUrl(completedData.trace_url);
          setActiveRunId(null);
          await loadArticles();
          if (completedData.article_id) {
            await loadArticleDetail(completedData.article_id);
          }
        }
      );

      sseClientRef.current = sse;
      sse.connect();
    } catch (err: any) {
      setRunError(err.message || "Failed to start run.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancelRun = async () => {
    if (!activeRunId) return;
    try {
      await api.cancelRun(activeRunId);
      if (sseClientRef.current) sseClientRef.current.close();
      setActiveRunId(null);
      setRunError("Research run was cancelled.");
    } catch (err) {
      console.error("Cancel failed:", err);
    }
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    setArticles([]);
    setSelectedArticle(null);
    setIsAuthOpen(true);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-indigo-500/30">
      {/* 1. Studio Header */}
      <header className="sticky top-0 z-40 w-full border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-gradient-to-tr from-indigo-600 to-violet-600 rounded-xl shadow-lg shadow-indigo-500/20">
            <Sparkles className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Research & Visual Blog Studio
              <span className="px-2 py-0.5 text-[10px] uppercase font-mono font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md">
                v2.0 Next.js 15
              </span>
            </h1>
            <p className="text-xs text-slate-400">Autonomous 4-Agent Research Squad & Native Mermaid Canvas</p>
          </div>
        </div>

        {/* System & User Badges */}
        <div className="flex items-center gap-3">
          {systemStats && (
            <div className="hidden md:flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl text-xs text-slate-300">
              <Database className="w-3.5 h-3.5 text-indigo-400" />
              <span>{systemStats.database?.backend?.toUpperCase()}</span>
              <span className="text-slate-600">|</span>
              <span className="text-slate-400">
                L1/L2 Hits: {systemStats.cache?.metrics?.total_hits || 0}
              </span>
            </div>
          )}

          {user ? (
            <div className="flex items-center gap-2 pl-2">
              <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl text-xs">
                <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-slate-300 font-medium">{user.email}</span>
              </div>
              <button
                onClick={handleLogout}
                title="Log out"
                className="p-2 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-xl transition"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
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
              <Sparkles className="w-4 h-4 text-indigo-400" />
              Commission AI Squad
            </h2>

            <form onSubmit={handleStartRun} className="space-y-4">
              <div>
                <textarea
                  required
                  rows={3}
                  placeholder="Enter research topic, target domain, or prompt brief..."
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  className="w-full p-3.5 bg-slate-950 border border-slate-800 rounded-2xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-200 resize-none placeholder:text-slate-500"
                />
              </div>

              {/* Quick Presets */}
              <div>
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1.5">
                  Suggested Topics
                </span>
                <div className="flex flex-col gap-1.5">
                  {PRESET_TOPICS.map((pt, i) => (
                    <button
                      key={i}
                      type="button"
                      onClick={() => setTopic(pt)}
                      className="text-left px-2.5 py-1.5 bg-slate-950 hover:bg-slate-800/80 text-slate-300 hover:text-white rounded-lg text-xs truncate transition border border-slate-800/60"
                    >
                      {pt}
                    </button>
                  ))}
                </div>
              </div>

              {/* Advanced Controls Toggle */}
              <div>
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="flex items-center justify-between w-full py-1.5 text-xs text-slate-400 hover:text-slate-200 transition"
                >
                  <span className="flex items-center gap-1.5 font-medium">
                    <SlidersHorizontal className="w-3.5 h-3.5" />
                    Tone & Audience Options
                  </span>
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`} />
                </button>

                {showAdvanced && (
                  <div className="pt-3 space-y-3 border-t border-slate-800 mt-2">
                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Tone of Voice</label>
                      <select
                        value={tone}
                        onChange={(e) => setTone(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200"
                      >
                        <option>Professional & Authoritative</option>
                        <option>Engaging & Accessible</option>
                        <option>Academic & Rigorous</option>
                        <option>Executive Brief</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] text-slate-400 mb-1">Target Audience</label>
                      <select
                        value={audience}
                        onChange={(e) => setAudience(e.target.value)}
                        className="w-full p-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200"
                      >
                        <option>Software Engineers & Developers</option>
                        <option>CTOs & Tech Leaders</option>
                        <option>Product Managers</option>
                        <option>General Tech Enthusiasts</option>
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
                <Sparkles className="w-4 h-4" />
                {isSubmitting ? "Launching Squad..." : "Launch Research Squad"}
              </button>
            </form>

            {runError && (
              <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400">
                {runError}
              </div>
            )}
          </div>

          {/* Past Articles Library */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 shadow-xl backdrop-blur-sm flex-1 flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                Your Articles Library ({articles.length})
              </h3>
            </div>

            <div className="space-y-2 overflow-y-auto max-h-96 pr-1 divide-y divide-slate-800/40">
              {articles.map((art) => (
                <div
                  key={art.id}
                  onClick={() => loadArticleDetail(art.id)}
                  className={`pt-2 cursor-pointer p-3 rounded-xl transition ${
                    selectedArticle?.id === art.id
                      ? "bg-indigo-950/40 border border-indigo-500/40 text-slate-100"
                      : "hover:bg-slate-800/40 text-slate-300"
                  }`}
                >
                  <h4 className="text-xs font-semibold line-clamp-1 mb-1">{art.topic}</h4>
                  <div className="flex items-center gap-2 text-[10px] text-slate-500">
                    <span>{art.word_count.toLocaleString()} words</span>
                    <span>&bull;</span>
                    <span>{art.created_at}</span>
                  </div>
                </div>
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
              onCancel={handleCancelRun}
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
                <BookOpen className="w-8 h-8" />
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
          onArticleRestored={() => loadArticleDetail(selectedArticle.id)}
        />
      )}

      {/* 4. Passwordless Auth Modal */}
      <AuthDialog
        isOpen={isAuthOpen}
        onSuccess={(u) => {
          setUser(u);
          setIsAuthOpen(false);
          loadArticles();
          loadTelemetry();
        }}
        onClose={() => setIsAuthOpen(false)}
      />
    </div>
  );
}
