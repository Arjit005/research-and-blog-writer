"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import mermaid from "mermaid";
import {
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Maximize2,
  Minimize2,
  Copy,
  Check,
  Download,
  Code2,
  Eye,
  AlertTriangle,
  Move,
} from "lucide-react";

interface MermaidCanvasProps {
  code: string;
  title?: string;
  caption?: string;
}

const MERMAID_CONFIG = {
  startOnLoad: false,
  theme: "dark",
  securityLevel: "strict",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  themeVariables: {
    darkMode: true,
    background: "#030712",
    primaryColor: "#4f46e5",
    primaryTextColor: "#f1f5f9",
    primaryBorderColor: "#6366f1",
    lineColor: "#94a3b8",
    secondaryColor: "#0f172a",
    tertiaryColor: "#1e293b",
    mainBkg: "#0f172a",
    nodeBorder: "#4338ca",
    clusterBkg: "#090d16",
    clusterBorder: "#334155",
    titleColor: "#e2e8f0",
    edgeLabelBackground: "#0b0f19",
  },
} satisfies Parameters<typeof mermaid.initialize>[0];

let mermaidInitialized = false;
let mermaidRenderCounter = 0;

function ensureMermaidInitialized(): void {
  if (mermaidInitialized) return;
  mermaid.initialize(MERMAID_CONFIG);
  mermaidInitialized = true;
}

/**
 * Clean & sanitize diagram code before passing to Mermaid 12.3.0.
 * Strips accidental wrapping backticks or HTML entities.
 */
function sanitizeMermaidSource(raw: string): string {
  let cleaned = raw.trim();
  // Remove markdown code fences if wrapped inside
  if (cleaned.startsWith("```mermaid")) {
    cleaned = cleaned.replace(/^```mermaid\s*/i, "");
  } else if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```\s*/, "");
  }
  if (cleaned.endsWith("```")) {
    cleaned = cleaned.replace(/```\s*$/, "");
  }

  // Trim again
  cleaned = cleaned.trim();

  // If there's no initial directive, default to flowchart TD if it looks like node connections
  if (
    !/^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|gitGraph|mindmap|timeline|quadrantChart|C4Context|xychart-beta)\b/i.test(
      cleaned
    )
  ) {
    if (cleaned.includes("-->") || cleaned.includes("---")) {
      cleaned = `flowchart TD\n${cleaned}`;
    }
  }

  return cleaned;
}

export function MermaidCanvas({
  code,
  title = "Architecture & Dataflow Blueprint",
  caption,
}: MermaidCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderTokenRef = useRef(0);
  const [svgContent, setSvgContent] = useState<string>("");
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number>(1);
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showSource, setShowSource] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  const cleanSource = sanitizeMermaidSource(code);

  const renderDiagram = useCallback(async (sourceText: string, token: number) => {
    try {
      ensureMermaidInitialized();
      const id = `mermaid-canvas-svg-${++mermaidRenderCounter}`;
      
      // Use parse first to validate syntax if supported
      try {
        await mermaid.parse(sourceText);
      } catch (parseErr) {
        if (token !== renderTokenRef.current) return;
        const msg = parseErr instanceof Error ? parseErr.message : String(parseErr);
        setErrorDetails(msg || "Syntax error in Mermaid specification.");
        return;
      }

      const { svg } = await mermaid.render(id, sourceText);

      if (token !== renderTokenRef.current) return;

      if (typeof svg !== "string" || !svg.trimStart().startsWith("<svg")) {
        throw new Error("Unexpected Mermaid render output: invalid SVG root.");
      }
      if (/<script[\s>]/i.test(svg)) {
        throw new Error("Refused Mermaid output containing a script tag.");
      }

      setSvgContent(svg);
      setErrorDetails(null);
    } catch (err: unknown) {
      if (token !== renderTokenRef.current) return;
      console.error("Mermaid rendering exception:", err);
      const msg = err instanceof Error ? err.message : String(err);
      setErrorDetails(msg || "Could not render diagram. Please review the Mermaid code syntax.");
    }
  }, []);

  useEffect(() => {
    const token = ++renderTokenRef.current;
    if (!cleanSource) {
      setSvgContent("");
      setErrorDetails(null);
      return;
    }
    void renderDiagram(cleanSource, token);
  }, [cleanSource, renderDiagram]);

  const handleCopyCode = () => {
    void navigator.clipboard.writeText(cleanSource).catch((err: unknown) => {
      console.error("Clipboard write failed:", err);
    });
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSvg = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.svg`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handleFitToScreen = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  // Pointer pan controls with pointer capture (supporting mouse, touch, and pen)
  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (showSource || errorDetails) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Best-effort pointer capture
    }
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    setIsDragging(false);
    try {
      if (e.currentTarget.hasPointerCapture(e.pointerId)) {
        e.currentTarget.releasePointerCapture(e.pointerId);
      }
    } catch {
      // Best-effort release
    }
  };

  if ((!code || !cleanSource) && !svgContent) return null;

  return (
    <div
      className={`my-8 rounded-2xl border border-slate-800/80 bg-slate-950 shadow-2xl overflow-hidden transition-all duration-200 ${
        isFullscreen
          ? "fixed inset-3 md:inset-8 z-50 flex flex-col bg-slate-950/98 border-slate-700 backdrop-blur-xl"
          : "relative"
      }`}
    >
      {/* Canvas Top Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-slate-900/80 border-b border-slate-800/80 backdrop-blur-md">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-2 w-2 relative shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
          </span>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-200 truncate font-mono">
            {title}
          </h4>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowSource(!showSource)}
            title={showSource ? "View Visual Diagram" : "View Mermaid Source"}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition ${
              showSource
                ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/40"
                : "bg-slate-800/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-transparent"
            }`}
          >
            {showSource ? <Eye className="w-3.5 h-3.5" /> : <Code2 className="w-3.5 h-3.5" />}
            <span className="hidden sm:inline">{showSource ? "Diagram" : "Source"}</span>
          </button>

          <div className="w-px h-4 bg-slate-800 mx-1" />

          {/* Zoom controls */}
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(z + 0.2, 3))}
            title="Zoom In"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.4))}
            title="Zoom Out"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={handleFitToScreen}
            title="Fit to Screen (Reset View)"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <div className="w-px h-4 bg-slate-800 mx-1" />

          {/* Copy Source */}
          <button
            type="button"
            onClick={handleCopyCode}
            title="Copy Mermaid Code"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>

          {/* Download SVG */}
          <button
            type="button"
            onClick={handleDownloadSvg}
            disabled={!svgContent}
            title="Export as SVG"
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 disabled:opacity-30 rounded-lg transition"
          >
            <Download className="w-4 h-4" />
          </button>

          {/* Fullscreen */}
          <button
            type="button"
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen Canvas"}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 rounded-lg transition"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Main Viewport */}
      <div
        ref={containerRef}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerUp}
        className={`relative w-full overflow-hidden flex items-center justify-center p-6 select-none touch-none ${
          isFullscreen ? "flex-1 min-h-[500px]" : "min-h-[360px] max-h-[640px]"
        } ${isDragging ? "cursor-grabbing" : "cursor-grab"}`}
        style={{
          backgroundImage: "radial-gradient(#1e293b 1px, transparent 1px)",
          backgroundSize: "24px 24px",
        }}
      >
        {/* Source view tab */}
        {showSource ? (
          <div className="w-full h-full max-h-[480px] overflow-auto bg-slate-950 p-4 rounded-xl border border-slate-800">
            <div className="flex items-center justify-between text-xs text-slate-400 mb-2 font-mono">
              <span>Mermaid 12.3.0 Compatible Code</span>
              <span className="text-slate-500">{cleanSource.split("\n").length} lines</span>
            </div>
            <pre className="font-mono text-xs text-indigo-300 leading-relaxed overflow-x-auto selection:bg-indigo-600/30">
              <code>{cleanSource}</code>
            </pre>
          </div>
        ) : errorDetails ? (
          /* Error State with fallback and diagnostic */
          <div className="w-full max-w-xl mx-auto p-6 rounded-2xl bg-amber-500/5 border border-amber-500/20 text-center">
            <div className="inline-flex p-3 bg-amber-500/10 rounded-xl text-amber-400 mb-3">
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h5 className="text-sm font-semibold text-slate-200 mb-1">
              Mermaid Diagram Rendering Issue
            </h5>
            <p className="text-xs text-slate-400 mb-4 max-w-md mx-auto">
              The diagram specification contains a syntax variation that could not be parsed by
              Mermaid 12.3. The original source has been safely preserved below.
            </p>
            <div className="text-left bg-slate-950 border border-slate-800 p-3.5 rounded-xl font-mono text-[11px] text-amber-300/90 mb-3 max-h-32 overflow-y-auto">
              <span className="text-slate-500 font-bold block mb-1">Parser details:</span>
              {errorDetails}
            </div>
            <div className="text-left bg-slate-900/90 border border-slate-800 p-3.5 rounded-xl font-mono text-xs text-slate-300 max-h-48 overflow-auto">
              <pre className="text-slate-400">
                <code>{cleanSource}</code>
              </pre>
            </div>
          </div>
        ) : svgContent ? (
          /* Rendered Interactive SVG with Zoom & Pan */
          <div
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: "center center",
              transition: isDragging ? "none" : "transform 0.1s ease-out",
            }}
            className="max-w-none transition-transform pointer-events-none"
            dangerouslySetInnerHTML={{ __html: svgContent }}
          />
        ) : (
          <div className="flex flex-col items-center gap-2 text-xs text-slate-500">
            <span className="animate-pulse">Synthesizing diagram SVG…</span>
          </div>
        )}

        {/* Pan helper hint */}
        {!showSource && !errorDetails && svgContent && (
          <div className="absolute bottom-3 left-4 flex items-center gap-1.5 px-2.5 py-1 bg-slate-900/70 border border-slate-800/80 rounded-md text-[10px] text-slate-400 backdrop-blur-sm pointer-events-none">
            <Move className="w-3 h-3 text-slate-500" />
            <span>Drag to pan · Scroll/buttons to zoom ({Math.round(zoom * 100)}%)</span>
          </div>
        )}
      </div>

      {/* Optional Caption Footer */}
      {caption && (
        <div className="px-5 py-2.5 bg-slate-900/60 border-t border-slate-800/60 text-xs text-slate-400 italic">
          <span className="font-semibold text-slate-300 not-italic mr-1.5">Figure note:</span>
          {caption}
        </div>
      )}
    </div>
  );
}