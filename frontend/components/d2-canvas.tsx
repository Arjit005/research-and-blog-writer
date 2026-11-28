"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Code2,
  Copy,
  Download,
  Eye,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

interface D2CanvasProps {
  code: string;
  title?: string;
  caption?: string;
  className?: string;
}

export function D2Canvas({
  code,
  title = "System Architecture Diagram",
  caption,
  className = "",
}: D2CanvasProps) {
  const [svgUrl, setSvgUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState(false);

  const cleanSource = (code || "")
    .trim()
    .replace(/^```d2\s*/i, "")
    .replace(/```\s*$/, "")
    .trim();

  useEffect(() => {
    let disposed = false;
    let objectUrl: string | null = null;
    let timeoutId: number | undefined;
    let d2Instance: { dispose?: () => Promise<void> } | null = null;

    const renderD2 = async () => {
      setError(null);
      setSvgUrl(null);
      try {
        const renderableCode = cleanSource;
        if (!renderableCode) {
          setError("Empty D2 diagram source.");
          return;
        }
        const { D2 } = await import("@d2lang/d2");
        if (disposed) return;
        const d2 = new D2();
        d2Instance = d2 as unknown as { dispose?: () => Promise<void> };
        timeoutId = window.setTimeout(() => {
          void d2Instance?.dispose?.();
          if (!disposed) setError("Rendering took too long. Try simplifying or splitting this diagram.");
        }, 15_000);
        const result = await d2.compile(renderableCode, { layout: "dagre", themeID: 0 });
        if (disposed) return;
        const svg = await d2.render(result.diagram, {
          ...result.renderOptions,
          center: true,
          pad: 12,
          themeID: 0,
          noXMLTag: true,
        });
        if (disposed) return;

        objectUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        setSvgUrl(objectUrl);
      } catch (renderError) {
        if (!disposed) {
          setError(renderError instanceof Error ? renderError.message : "Could not render this D2 diagram.");
        }
      } finally {
        if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      }
    };

    void renderD2();
    return () => {
      disposed = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      void d2Instance?.dispose?.();
    };
  }, [cleanSource]);

  const handleCopyCode = useCallback(() => {
    if (!cleanSource) return;
    navigator.clipboard.writeText(cleanSource);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [cleanSource]);

  const handleDownloadSvg = useCallback(() => {
    if (!svgUrl) return;
    const anchor = document.createElement("a");
    anchor.href = svgUrl;
    anchor.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "diagram"}.svg`;
    anchor.click();
  }, [svgUrl, title]);

  const handleResetView = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);

  const handlePointerDown = (e: React.PointerEvent) => {
    if (showSource || error) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    if (!isDragging) return;
    setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    if (!isDragging) return;
    setIsDragging(false);
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      // ignore
    }
  };

  return (
    <div
      className={`d2-card rounded-2xl border border-border bg-surface/90 overflow-hidden shadow-2xl transition-all duration-300 ${
        isFullscreen ? "fixed inset-3 md:inset-8 z-50 flex flex-col bg-background/98 backdrop-blur-xl" : "relative"
      } ${className}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-surface/80 border-b border-border/80">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="h-2 w-2 rounded-full bg-signal shrink-0" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-foreground truncate font-mono">
            {title}
          </h4>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowSource((prev) => !prev)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-surface-raised/60 text-muted-foreground hover:text-foreground hover:bg-surface-raised transition"
          >
            {showSource ? <Eye className="w-3.5 h-3.5" /> : <Code2 className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{showSource ? "Diagram" : "Source"}</span>
          </button>
          <div className="w-px h-4 bg-surface-raised mx-1" />
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(z + 0.25, 3))}
            title="Zoom In"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(z - 0.25, 0.4))}
            title="Zoom Out"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleResetView}
            title="Reset View"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <div className="w-px h-4 bg-surface-raised mx-1" />
          <button
            type="button"
            onClick={handleCopyCode}
            title="Copy D2 Code"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>
          <button
            type="button"
            onClick={handleDownloadSvg}
            disabled={!svgUrl}
            title="Download SVG"
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition disabled:opacity-40"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setIsFullscreen((f) => !f)}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-surface-raised/80 rounded-lg transition"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      <div
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className={`flex max-h-[640px] w-full items-center justify-center overflow-auto p-2 select-none touch-none ${
          isFullscreen ? "flex-1 min-h-[500px]" : ""
        } ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
        style={{
          backgroundColor: "#FAFAFA",
          backgroundImage: "radial-gradient(#d4d4d8 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      >
        {showSource ? (
          <pre className="w-full max-h-[480px] overflow-auto rounded-xl border border-border bg-background p-4 font-mono text-xs text-signal">
            <code>{cleanSource}</code>
          </pre>
        ) : error ? (
          <div className="max-w-lg rounded-2xl border border-amber-500/20 bg-amber-500/5 p-6 text-center">
            <AlertTriangle className="mx-auto mb-2 h-6 w-6 text-amber-400" />
            <p className="text-xs text-muted-foreground">{error}</p>
          </div>
        ) : svgUrl ? (
          <div
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.1s ease-out",
            }}
          >
            <img src={svgUrl} alt={title} className="max-w-none h-auto" />
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-muted-foreground py-12">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Rendering D2 architecture diagram...</span>
          </div>
        )}
      </div>

      {caption && (
        <div className="border-t border-border/60 bg-surface/60 px-4 py-2.5 text-center text-[11px] italic text-muted-foreground">
          {caption}
        </div>
      )}
    </div>
  );
}
