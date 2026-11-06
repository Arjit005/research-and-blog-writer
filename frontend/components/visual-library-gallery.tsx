"use client";

import React, { useState, useMemo } from "react";
import {
  Grid,
  List,
  Search,
  ExternalLink,
  Sparkles,
  FileCode,
  Image as ImageIcon,
  Trash2,
  ShieldCheck,
  FolderOpen,
} from "lucide-react";
import { ResearchVisual } from "@/lib/api";

interface VisualLibraryGalleryProps {
  visuals: ResearchVisual[];
  onSelectVisual: (index: number) => void;
  onDeleteVisual?: (id: number) => void;
  onOpenEvidence?: (visual: ResearchVisual) => void;
}

export function VisualLibraryGallery({
  visuals,
  onSelectVisual,
  onDeleteVisual,
  onOpenEvidence,
}: VisualLibraryGalleryProps) {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [originFilter, setOriginFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");

  // Filtering
  const filtered = useMemo(() => {
    return visuals.filter((v) => {
      const matchType = typeFilter === "all" || v.visual_type === typeFilter;
      const matchOrigin = originFilter === "all" || v.origin_type === originFilter;
      const q = search.toLowerCase();
      const matchSearch =
        !search.trim() ||
        v.title.toLowerCase().includes(q) ||
        (v.caption && v.caption.toLowerCase().includes(q)) ||
        (v.description && v.description.toLowerCase().includes(q));
      return matchType && matchOrigin && matchSearch;
    });
  }, [visuals, search, typeFilter, originFilter]);

  const categories = ["all", "diagram", "chart", "figure", "illustration"];
  const origins = ["all", "system_diagram", "retrieved_web", "ai_generated", "user_uploaded"];

  return (
    <div className="w-full flex flex-col gap-6">
      {/* 1. Gallery Search, Filter & View Controls */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 p-4 bg-slate-900/80 border border-slate-800 rounded-2xl backdrop-blur-md">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-500 absolute left-3.5 top-3" />
          <input
            type="text"
            placeholder="Search figures, diagrams, citations…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-sans"
          />
        </div>

        {/* Filters and View toggles */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Type Filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
            <span>Type:</span>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none"
            >
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Origin Filter */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
            <span>Origin:</span>
            <select
              value={originFilter}
              onChange={(e) => setOriginFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 rounded-lg px-2.5 py-1.5 text-xs focus:outline-none"
            >
              {origins.map((o) => (
                <option key={o} value={o}>
                  {o.replace(/_/g, " ").toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Grid vs List toggle */}
          <div className="flex items-center bg-slate-950 border border-slate-800 rounded-xl p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded-lg transition ${
                viewMode === "grid" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
              title="Grid View"
            >
              <Grid className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("list")}
              className={`p-1.5 rounded-lg transition ${
                viewMode === "list" ? "bg-indigo-600 text-white" : "text-slate-400 hover:text-slate-200"
              }`}
              title="List View"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* 2. Visual Cards Container */}
      {filtered.length === 0 ? (
        <div className="p-16 text-center bg-slate-900/40 border border-slate-800 rounded-3xl flex flex-col items-center justify-center">
          <FolderOpen className="w-10 h-10 text-slate-600 mb-3" />
          <h4 className="text-sm font-semibold text-slate-300">No Visual Assets Found</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-sm">
            {search || typeFilter !== "all" || originFilter !== "all"
              ? "No visuals match your search query and filters."
              : "Launch a research run to automatically synthesize architecture diagrams, extract figures, and build interactive charts."}
          </p>
        </div>
      ) : viewMode === "grid" ? (
        /* Grid Layout */
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {filtered.map((item, idx) => {
            const isDiagram = item.visual_type === "diagram" || item.origin_type === "system_diagram";
            const isAI = item.origin_type === "ai_generated";

            return (
              <div
                key={item.id}
                className="group relative flex flex-col bg-slate-900/70 border border-slate-800/80 hover:border-indigo-500/50 rounded-2xl overflow-hidden shadow-lg hover:shadow-indigo-500/10 transition-all duration-200"
              >
                {/* Thumbnail Preview Area */}
                <div
                  onClick={() => onSelectVisual(idx)}
                  className="relative aspect-video w-full bg-slate-950 flex items-center justify-center overflow-hidden cursor-pointer border-b border-slate-800/70"
                >
                  {isDiagram ? (
                    <div className="p-4 w-full h-full flex flex-col justify-center items-center bg-slate-950 text-indigo-400/90 group-hover:text-indigo-300 transition">
                      <FileCode className="w-8 h-8 mb-2" />
                      <span className="text-[11px] font-mono font-semibold">Mermaid Architecture</span>
                      <span className="text-[10px] text-slate-500 font-mono mt-1">Click to view & zoom</span>
                    </div>
                  ) : item.thumbnail_url || item.source_url ? (
                    <img
                      src={item.thumbnail_url || item.source_url || ""}
                      alt={item.alt_text || item.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex flex-col items-center justify-center text-slate-600">
                      <ImageIcon className="w-8 h-8 mb-1" />
                      <span className="text-[10px] font-mono">Visual Asset</span>
                    </div>
                  )}

                  {/* Badges on Thumbnail */}
                  <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5">
                    <span className="px-2 py-0.5 text-[10px] font-mono font-semibold uppercase rounded-md bg-slate-900/80 text-slate-300 border border-slate-700/60 backdrop-blur-sm">
                      {item.visual_type}
                    </span>
                    {isAI && (
                      <span className="px-2 py-0.5 text-[10px] font-mono font-semibold rounded-md bg-amber-500/20 text-amber-300 border border-amber-500/40 backdrop-blur-sm flex items-center gap-1">
                        <Sparkles className="w-3 h-3" />
                        AI
                      </span>
                    )}
                  </div>
                </div>

                {/* Card Meta & Action Body */}
                <div className="p-4 flex-1 flex flex-col justify-between">
                  <div>
                    <h4
                      onClick={() => onSelectVisual(idx)}
                      className="text-xs font-bold text-slate-200 group-hover:text-indigo-300 line-clamp-1 cursor-pointer transition"
                    >
                      {item.title}
                    </h4>
                    {item.caption && (
                      <p className="text-[11px] text-slate-400 line-clamp-2 mt-1 leading-relaxed">
                        {item.caption}
                      </p>
                    )}
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono text-slate-500">
                    <span className="capitalize">{item.origin_type.replace(/_/g, " ")}</span>

                    <div className="flex items-center gap-1.5">
                      {onOpenEvidence && (
                        <button
                          type="button"
                          onClick={() => onOpenEvidence(item)}
                          className="p-1 hover:text-emerald-400 transition"
                          title="Verify Evidence Link"
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {item.source_url && (
                        <a
                          href={item.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1 hover:text-indigo-400 transition"
                          title="Open Source Link"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                      {onDeleteVisual && (
                        <button
                          type="button"
                          onClick={() => onDeleteVisual(item.id)}
                          className="p-1 hover:text-rose-400 transition cursor-pointer"
                          title="Delete from Library"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* List Layout */
        <div className="rounded-2xl border border-slate-800 bg-slate-900/60 divide-y divide-slate-800 overflow-hidden font-mono text-xs">
          {filtered.map((item, idx) => (
            <div
              key={item.id}
              className="flex items-center justify-between p-4 hover:bg-slate-800/40 transition gap-4"
            >
              <div
                onClick={() => onSelectVisual(idx)}
                className="flex items-center gap-3.5 min-w-0 flex-1 cursor-pointer"
              >
                <div className="w-12 h-12 rounded-xl bg-slate-950 border border-slate-800 shrink-0 overflow-hidden flex items-center justify-center">
                  {item.thumbnail_url || item.source_url ? (
                    <img
                      src={item.thumbnail_url || item.source_url || ""}
                      alt={item.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <FileCode className="w-5 h-5 text-indigo-400" />
                  )}
                </div>
                <div className="min-w-0">
                  <h4 className="text-xs font-bold text-slate-200 truncate">{item.title}</h4>
                  <div className="flex items-center gap-2 text-[10px] text-slate-400 mt-0.5">
                    <span className="capitalize">{item.visual_type}</span>
                    <span>·</span>
                    <span className="capitalize">{item.origin_type.replace(/_/g, " ")}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {onOpenEvidence && (
                  <button
                    type="button"
                    onClick={() => onOpenEvidence(item)}
                    className="p-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
                    title="Trace Evidence"
                  >
                    <ShieldCheck className="w-3.5 h-3.5" />
                  </button>
                )}
                {onDeleteVisual && (
                  <button
                    type="button"
                    onClick={() => onDeleteVisual(item.id)}
                    className="p-1.5 bg-slate-800 hover:bg-rose-500/20 text-slate-400 hover:text-rose-400 rounded-lg transition cursor-pointer"
                    title="Delete"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
