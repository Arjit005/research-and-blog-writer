"use client";

import React, { useState, useMemo } from "react";
import { ArticleSummary } from "@/lib/api";
import {
  Sparkles,
  BookOpen,
  Search,
  SlidersHorizontal,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  FolderOpen,
} from "lucide-react";

interface LeftSidebarProps {
  topic: string;
  setTopic: (topic: string) => void;
  tone: string;
  setTone: (tone: string) => void;
  audience: string;
  setAudience: (audience: string) => void;
  targetLength: string;
  setTargetLength: (length: string) => void;
  isSubmitting: boolean;
  activeRunId: string | null;
  onSubmit: (e: React.FormEvent) => void;
  articles: ArticleSummary[];
  selectedArticleId: number | null;
  onSelectArticle: (id: number) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
}

const PRESET_TOPICS = [
  "Autonomous Multi-Agent AI Systems: 2026 Architecture",
  "Quantum Computing Advancements in Post-RSA Cryptography",
  "High-Throughput Event-Driven Microservices in Rust & Go",
  "Zero-Knowledge Proofs in Enterprise Cloud Security",
];

export function LeftSidebar({
  topic,
  setTopic,
  tone,
  setTone,
  audience,
  setAudience,
  targetLength,
  setTargetLength,
  isSubmitting,
  activeRunId,
  onSubmit,
  articles,
  selectedArticleId,
  onSelectArticle,
  isCollapsed,
  onToggleCollapse,
}: LeftSidebarProps) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredArticles = useMemo(() => {
    if (!searchQuery.trim()) return articles;
    const q = searchQuery.toLowerCase();
    return articles.filter(
      (a) =>
        a.topic.toLowerCase().includes(q) ||
        a.tone?.toLowerCase().includes(q) ||
        a.audience?.toLowerCase().includes(q)
    );
  }, [articles, searchQuery]);

  if (isCollapsed) {
    return (
      <div className="hidden lg:flex flex-col items-center gap-4 p-3 bg-slate-900/80 hover:bg-slate-900 border border-slate-800 rounded-2xl text-slate-400 hover:text-slate-200 transition shadow-xl w-14 shrink-0">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="p-1.5 hover:bg-slate-800 rounded-lg text-slate-300 transition"
          title="Expand Research Workspace Sidebar"
        >
          <ChevronRight className="w-5 h-5 text-indigo-400" />
        </button>
        <span className="text-[10px] font-mono uppercase tracking-widest [writing-mode:vertical-rl] rotate-180 text-slate-400 font-semibold">
          Articles & Controls ({articles.length})
        </span>
      </div>
    );
  }

  return (
    <aside className="w-full lg:w-80 xl:w-92 shrink-0 flex flex-col gap-5 text-slate-100">
      {/* 1. Research Commission Box */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 md:p-5 shadow-xl backdrop-blur-md">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/70">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-indigo-400" aria-hidden="true" />
            Commission Research
          </h2>
          <button
            type="button"
            onClick={onToggleCollapse}
            className="hidden lg:block p-1 text-slate-400 hover:text-slate-200 rounded hover:bg-slate-800 transition"
            title="Collapse Sidebar"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-3.5">
          <div>
            <label htmlFor="research-topic-input" className="sr-only">
              Research Topic
            </label>
            <textarea
              id="research-topic-input"
              required
              rows={3}
              placeholder="Enter research topic, architectural domain, or prompt brief…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              className="w-full p-3 bg-slate-950 border border-slate-800 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 text-slate-200 resize-none placeholder:text-slate-500 leading-relaxed"
            />
          </div>

          {/* Preset Topics */}
          <div>
            <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block mb-1.5 font-mono">
              Suggested Topics
            </span>
            <div className="flex flex-col gap-1">
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

          {/* Tone & Audience Options */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              aria-expanded={showAdvanced}
              className="flex items-center justify-between w-full py-1 text-xs text-slate-400 hover:text-slate-200 transition"
            >
              <span className="flex items-center gap-1.5 font-medium">
                <SlidersHorizontal className="w-3 h-3 text-indigo-400" aria-hidden="true" />
                Tone & Scope Controls
              </span>
              <ChevronDown
                className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
            </button>

            {showAdvanced && (
              <div className="pt-3 space-y-2.5 border-t border-slate-800/70 mt-2">
                <div>
                  <label htmlFor="tone-select-box" className="block text-[11px] text-slate-400 mb-1">
                    Tone of Voice
                  </label>
                  <select
                    id="tone-select-box"
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
                  <label htmlFor="audience-select-box" className="block text-[11px] text-slate-400 mb-1">
                    Target Audience
                  </label>
                  <select
                    id="audience-select-box"
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

                <div>
                  <label htmlFor="length-select-box" className="block text-[11px] text-slate-400 mb-1">
                    Target Depth
                  </label>
                  <select
                    id="length-select-box"
                    value={targetLength}
                    onChange={(e) => setTargetLength(e.target.value)}
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

          {/* Launch Button */}
          <button
            type="submit"
            disabled={isSubmitting || !!activeRunId || !topic.trim()}
            className="w-full py-2.5 px-4 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 disabled:opacity-50 text-white font-semibold rounded-xl text-xs transition shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2 cursor-pointer disabled:cursor-not-allowed"
          >
            <Sparkles className="w-4 h-4" aria-hidden="true" />
            <span>{isSubmitting ? "Dispatching Squad…" : "Launch Research Squad"}</span>
          </button>
        </form>
      </div>

      {/* 2. Articles Library with Search & Filtering */}
      <div className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 md:p-5 shadow-xl backdrop-blur-md flex-1 flex flex-col min-h-[300px]">
        <div className="flex items-center justify-between mb-3 pb-2 border-b border-slate-800/70">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200 flex items-center gap-2">
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />
            Articles Library
            <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-indigo-300 border border-slate-700/60">
              {articles.length}
            </span>
          </h3>
        </div>

        {/* Search Bar */}
        <div className="relative mb-3">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search articles & topics…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Articles List */}
        <div className="space-y-2 overflow-y-auto max-h-[380px] pr-1 divide-y divide-slate-800/40 flex-1">
          {filteredArticles.map((article) => {
            const isSelected = selectedArticleId === article.id;
            return (
              <button
                key={article.id}
                type="button"
                onClick={() => onSelectArticle(article.id)}
                className={`w-full text-left pt-2.5 p-3 rounded-xl transition cursor-pointer ${
                  isSelected
                    ? "bg-indigo-950/40 border border-indigo-500/50 text-slate-100 shadow-md"
                    : "hover:bg-slate-800/40 text-slate-300 border border-transparent"
                }`}
              >
                <h4 className="text-xs font-semibold line-clamp-2 mb-1.5 leading-snug">
                  {article.topic}
                </h4>
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span>{article.word_count.toLocaleString()} words</span>
                  <span>{article.created_at?.split("T")[0] || article.created_at}</span>
                </div>
              </button>
            );
          })}

          {filteredArticles.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-500 italic flex flex-col items-center gap-2">
              <FolderOpen className="w-6 h-6 text-slate-600" />
              <span>{searchQuery ? "No matching articles found." : "No articles recorded yet."}</span>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}