"use client";

import React, { useState, useEffect, useCallback } from "react";
import { MermaidCanvas } from "./mermaid-canvas";
import { D2Canvas } from "./d2-canvas";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  ExternalLink,
  ChevronLeft,
  ChevronRight,
  X,
  Copy,
  Check,
  Info,
  ShieldCheck,
  Sparkles,
  Layers,
} from "lucide-react";
import { ResearchVisual } from "@/lib/api";

interface ImageLightboxViewerProps {
  visuals: ResearchVisual[];
  currentIndex: number;
  isOpen: boolean;
  onClose: () => void;
  onIndexChange?: (newIndex: number) => void;
  onOpenEvidence?: (visual: ResearchVisual) => void;
}

export function ImageLightboxViewer({
  visuals,
  currentIndex,
  isOpen,
  onClose,
  onIndexChange,
  onOpenEvidence,
}: ImageLightboxViewerProps) {
  const [index, setIndex] = useState(currentIndex);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [showMetadata, setShowMetadata] = useState(true);
  const [copiedUrl, setCopiedUrl] = useState(false);

  useEffect(() => {
    setIndex(currentIndex);
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [currentIndex, isOpen]);

  const currentVisual = visuals[index] || null;

  const handleNext = useCallback(() => {
    if (index < visuals.length - 1) {
      const next = index + 1;
      setIndex(next);
      setZoom(1);
      setPan({ x: 0, y: 0 });
      onIndexChange?.(next);
    }
  }, [index, visuals.length, onIndexChange]);

  const handlePrev = useCallback(() => {
    if (index > 0) {
      const prev = index - 1;
      setIndex(prev);
      setZoom(1);
      setPan({ x: 0, y: 0 });
      onIndexChange?.(prev);
    }
  }, [index, onIndexChange]);

  const handleResetZoom = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const handleZoomIn = () => {
    setZoom((z) => Math.min(z + 0.3, 4));
  };

  const handleZoomOut = () => {
    setZoom((z) => Math.max(z - 0.3, 0.4));
  };

  // Keyboard Navigation: Esc, ArrowLeft, ArrowRight, +, -, 0
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowRight") {
        handleNext();
      } else if (e.key === "ArrowLeft") {
        handlePrev();
      } else if (e.key === "+" || e.key === "=") {
        handleZoomIn();
      } else if (e.key === "-") {
        handleZoomOut();
      } else if (e.key === "0") {
        handleResetZoom();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, handleNext, handlePrev, onClose]);

  // Pointer Pan Support
  const handlePointerDown = (e: React.PointerEvent) => {
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    setIsDragging(false);
    (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
  };

  const handleCopyLink = async () => {
    if (currentVisual?.source_url) {
      await navigator.clipboard.writeText(currentVisual.source_url);
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    }
  };

  if (!isOpen || !currentVisual) return null;

  const isDiagram = currentVisual.visual_type === "diagram" || currentVisual.origin_type === "system_diagram";
  const isD2Diagram = isDiagram && currentVisual.file_format?.toLowerCase() === "d2";
  const isAI = currentVisual.origin_type === "ai_generated";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Visual Viewer: ${currentVisual.title}`}
      className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-xl text-foreground select-none animate-in fade-in duration-200"
    >
      {/* 1. Header Toolbar */}
      <div className="flex items-center justify-between px-6 py-3.5 bg-surface/90 border-b border-border">
        <div className="flex items-center gap-3">
          <span className="text-xs font-mono px-2.5 py-1 rounded-md bg-surface-raised text-foreground border border-border">
            {index + 1} / {visuals.length}
          </span>
          <h2 className="text-sm font-bold text-foreground line-clamp-1 max-w-md">
            {currentVisual.title}
          </h2>
          {isDiagram && (
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-signal/20 text-signal border border-signal/30">
              Diagram
            </span>
          )}
          {isAI && (
            <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
              <Sparkles className="w-3 h-3" />
              AI Illustrated
            </span>
          )}
        </div>

        {/* Viewport Control Tools */}
        <div className="flex items-center gap-2">
          <div className={`flex items-center bg-background rounded-xl border border-border p-0.5 ${isDiagram && !isD2Diagram ? "hidden" : ""}`}>
            <button
              type="button"
              onClick={handleZoomIn}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised rounded-lg transition"
              title="Zoom In (+)"
              aria-label="Zoom in"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <span className="text-[11px] font-mono px-2 text-muted-foreground">
              {Math.round(zoom * 100)}%
            </span>
            <button
              type="button"
              onClick={handleZoomOut}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised rounded-lg transition"
              title="Zoom Out (-)"
              aria-label="Zoom out"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={handleResetZoom}
              className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised rounded-lg transition"
              title="Fit to Screen / Reset (0)"
              aria-label="Reset zoom"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>

          {currentVisual.source_url && (
            <button
              type="button"
              onClick={handleCopyLink}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-surface hover:bg-surface-raised border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
              title="Copy original source link"
            >
              {copiedUrl ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden sm:inline">{copiedUrl ? "Copied" : "Source Link"}</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowMetadata(!showMetadata)}
            className={`p-2 rounded-xl border transition ${
              showMetadata
                ? "bg-accent/20 text-signal border-signal/40"
                : "bg-surface text-muted-foreground border-border hover:text-foreground"
            }`}
            title="Toggle Metadata & Traceability Panel"
          >
            <Info className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={onClose}
            className="p-2 bg-surface hover:bg-rose-500/20 text-muted-foreground hover:text-rose-400 border border-border hover:border-rose-500/30 rounded-xl transition cursor-pointer"
            title="Close Viewer (Esc)"
            aria-label="Close viewer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 2. Main Stage with Canvas & Metadata Drawer */}
      <div className="flex-1 relative flex overflow-hidden">
        {/* Navigation Arrow: Previous */}
        {index > 0 && (
          <button
            type="button"
            onClick={handlePrev}
            className="absolute left-6 top-1/2 -translate-y-1/2 z-20 p-3 bg-surface/80 hover:bg-surface-raised border border-border text-foreground hover:text-white rounded-full backdrop-blur-md shadow-2xl transition"
            title="Previous Visual (Left Arrow)"
            aria-label="Previous visual"
          >
            <ChevronLeft className="w-6 h-6" />
          </button>
        )}

        {/* Navigation Arrow: Next */}
        {index < visuals.length - 1 && (
          <button
            type="button"
            onClick={handleNext}
            className="absolute right-6 top-1/2 -translate-y-1/2 z-20 p-3 bg-surface/80 hover:bg-surface-raised border border-border text-foreground hover:text-white rounded-full backdrop-blur-md shadow-2xl transition"
            title="Next Visual (Right Arrow)"
            aria-label="Next visual"
          >
            <ChevronRight className="w-6 h-6" />
          </button>
        )}

        {/* Zoom & Pan Viewport Container */}
        <div
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          className={`flex-1 flex items-center justify-center p-8 overflow-hidden ${
            isDragging ? "cursor-grabbing" : "cursor-grab"
          }`}
          style={{
            backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
            backgroundSize: "28px 28px",
          }}
        >
          <div
            style={{
              transform: isDiagram && !isD2Diagram ? undefined : `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.15s ease-out",
            }}
            className="max-w-full max-h-full flex items-center justify-center"
          >
            {isDiagram && currentVisual.media_content ? (
              isD2Diagram ? (
                <D2Canvas
                  code={currentVisual.media_content}
                  title={currentVisual.title}
                  caption={currentVisual.caption ?? undefined}
                  className="my-0 w-full max-w-[1200px]"
                />
              ) : (
                <MermaidCanvas
                  code={currentVisual.media_content}
                  title={currentVisual.title}
                  caption={currentVisual.caption ?? undefined}
                  className="my-0 w-full max-w-[1200px]"
                />
              )
            ) : currentVisual.thumbnail_url || currentVisual.source_url ? (
              <img
                src={currentVisual.thumbnail_url || currentVisual.source_url || ""}
                alt={currentVisual.alt_text || currentVisual.title}
                className="max-w-[85vw] max-h-[75vh] object-contain rounded-2xl shadow-2xl pointer-events-none"
              />
            ) : (
              <div className="p-12 text-center bg-surface border border-border rounded-2xl">
                <Layers className="w-12 h-12 text-muted-foreground mx-auto mb-3" />
                <p className="text-sm text-muted-foreground font-medium">Visual Asset Available as Metadata</p>
              </div>
            )}
          </div>
        </div>

        {/* 3. Collapsible Source & Evidence Information Sidebar */}
        {showMetadata && (
          <aside className="w-80 lg:w-96 bg-surface/90 border-l border-border p-6 flex flex-col gap-4 overflow-y-auto backdrop-blur-md">
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-signal font-mono">
                Visual Evidence Profile
              </span>
              <h3 className="text-base font-bold text-foreground mt-1 leading-snug">
                {currentVisual.title}
              </h3>
            </div>

            {currentVisual.caption && (
              <div className="p-3 bg-background/70 border border-border/80 rounded-xl text-xs text-foreground italic">
                {currentVisual.caption}
              </div>
            )}

            {currentVisual.description && (
              <p className="text-xs text-muted-foreground leading-relaxed">
                {currentVisual.description}
              </p>
            )}

            {/* Traceability Grid */}
            <div className="space-y-2.5 pt-3 border-t border-border/80 font-mono text-xs">
              <div className="flex justify-between items-center text-muted-foreground">
                <span className="text-muted-foreground">Origin:</span>
                <span className="text-foreground capitalize">{currentVisual.origin_type.replace(/_/g, " ")}</span>
              </div>
              <div className="flex justify-between items-center text-muted-foreground">
                <span className="text-muted-foreground">Visual Category:</span>
                <span className="text-foreground capitalize">{currentVisual.visual_type}</span>
              </div>
              {currentVisual.publisher && (
                <div className="flex justify-between items-center text-muted-foreground">
                  <span className="text-muted-foreground">Publisher:</span>
                  <span className="text-foreground truncate max-w-[180px]">{currentVisual.publisher}</span>
                </div>
              )}
              {currentVisual.publication_date && (
                <div className="flex justify-between items-center text-muted-foreground">
                  <span className="text-muted-foreground">Publication Date:</span>
                  <span className="text-foreground">{currentVisual.publication_date}</span>
                </div>
              )}
              <div className="flex justify-between items-center text-muted-foreground">
                <span className="text-muted-foreground">Retrieved:</span>
                <span className="text-foreground">{currentVisual.retrieval_timestamp.split("T")[0]}</span>
              </div>
              {currentVisual.license_information && (
                <div className="flex justify-between items-center text-muted-foreground">
                  <span className="text-muted-foreground">License:</span>
                  <span className="text-signal truncate max-w-[180px]">{currentVisual.license_information}</span>
                </div>
              )}
            </div>

            {/* Source Link & Evidence Actions */}
            <div className="pt-4 border-t border-border/80 space-y-2">
              {currentVisual.source_url && (
                <a
                  href={currentVisual.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full py-2 px-3 bg-accent/20 hover:bg-accent/30 border border-signal/40 text-signal rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition"
                >
                  <ExternalLink className="w-3.5 h-3.5" />
                  <span>Inspect Original Web Source</span>
                </a>
              )}

              {onOpenEvidence && (
                <button
                  type="button"
                  onClick={() => onOpenEvidence(currentVisual)}
                  className="w-full py-2 px-3 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/40 text-emerald-300 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition cursor-pointer"
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>Review Evidence Links</span>
                </button>
              )}
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
