"use client";

import React, { useEffect, useRef, useState } from "react";
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
} from "lucide-react";

interface MermaidCanvasProps {
  code: string;
  title?: string;
}

const MERMAID_CONFIG = {
  startOnLoad: false,
  theme: "dark",
  securityLevel: "strict",
  fontFamily: "inherit",
  themeVariables: {
    darkMode: true,
    background: "#020617",
    primaryColor: "#4f46e5",
    primaryTextColor: "#f8fafc",
    primaryBorderColor: "#6366f1",
    lineColor: "#94a3b8",
    secondaryColor: "#0f172a",
    tertiaryColor: "#1e293b",
  },
} satisfies Parameters<typeof mermaid.initialize>[0];

// Mermaid config is global to the library: initialize exactly once per page load
// with the hardened (`securityLevel: "strict"`) configuration.
let mermaidInitialized = false;
let mermaidRenderCounter = 0;

function ensureMermaidInitialized(): void {
  if (mermaidInitialized) return;
  mermaid.initialize(MERMAID_CONFIG);
  mermaidInitialized = true;
}

export function MermaidCanvas({ code, title = "System Architecture Diagram" }: MermaidCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const renderTokenRef = useRef(0);
  const [svgContent, setSvgContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    ensureMermaidInitialized();

    const trimmed = code?.trim() ?? "";
    if (!trimmed) {
      renderTokenRef.current += 1;
      setSvgContent("");
      setError(null);
      return;
    }

    // Any newer code change invalidates this render; only the latest token wins.
    const token = ++renderTokenRef.current;
    let cancelled = false;
    setError(null);

    const renderDiagram = async () => {
      try {
        const id = `mermaid-svg-${++mermaidRenderCounter}`;
        const { svg } = await mermaid.render(id, trimmed);

        if (cancelled || token !== renderTokenRef.current) return;

        // The only HTML we ever inject is Mermaid's own output, produced with
        // securityLevel "strict" (HTML labels are escaped/sanitized). Refuse
        // anything that does not look like an SVG document as defense in depth.
        if (typeof svg !== "string" || !svg.trimStart().startsWith("<svg")) {
          throw new Error("Unexpected Mermaid render output.");
        }
        if (/<script[\s>]/i.test(svg)) {
          throw new Error("Refused Mermaid output containing a script tag.");
        }

        setSvgContent(svg);
      } catch (err: unknown) {
        if (cancelled || token !== renderTokenRef.current) return;
        console.error("Mermaid render error:", err);
        setError("Could not render this Mermaid diagram. The syntax may be invalid.");
      }
    };

    void renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [code]);

  const handleCopyCode = () => {
    void navigator.clipboard.writeText(code).catch((err: unknown) => {
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
    anchor.download = "architecture_diagram.svg";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (!code && !svgContent) return null;

  return (
    <div
      className={`relative my-6 rounded-2xl border border-slate-800 bg-slate-950/80 backdrop-blur-md overflow-hidden transition-all ${
        isFullscreen
          ? "fixed inset-4 z-50 flex flex-col shadow-2xl bg-slate-950 border-slate-700"
          : "shadow-xl"
      }`}
    >
      {/* Diagram Toolbar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800/80 bg-slate-900/50">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse" aria-hidden="true" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h4>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setZoom((current) => Math.min(current + 0.2, 2.5))}
            title="Zoom In"
            aria-label="Zoom in on diagram"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <ZoomIn className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setZoom((current) => Math.max(current - 0.2, 0.5))}
            title="Zoom Out"
            aria-label="Zoom out of diagram"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <ZoomOut className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setZoom(1)}
            title="Reset Zoom"
            aria-label="Reset diagram zoom"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
          </button>
          <div className="w-px h-4 bg-slate-800 mx-1" />
          <button
            type="button"
            onClick={handleCopyCode}
            title="Copy Mermaid Code"
            aria-label="Copy Mermaid source code"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            {copied ? (
              <Check className="w-4 h-4 text-emerald-400" aria-hidden="true" />
            ) : (
              <Copy className="w-4 h-4" aria-hidden="true" />
            )}
          </button>
          <button
            type="button"
            onClick={handleDownloadSvg}
            title="Download SVG"
            aria-label="Download diagram as SVG"
            disabled={!svgContent}
            className="p-1.5 hover:bg-slate-800 disabled:opacity-40 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <Download className="w-4 h-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={() => setIsFullscreen((current) => !current)}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            aria-label={isFullscreen ? "Exit fullscreen diagram" : "View diagram fullscreen"}
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            {isFullscreen ? (
              <Minimize2 className="w-4 h-4" aria-hidden="true" />
            ) : (
              <Maximize2 className="w-4 h-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>

      {/* SVG Container with pan & zoom scale */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto p-6 flex items-center justify-center min-h-[320px] select-none"
        aria-busy={!svgContent && !error}
      >
        {error ? (
          <div role="alert" className="text-center p-6 text-sm text-slate-400">
            <p className="text-amber-400 mb-2">{error}</p>
            <pre className="text-xs bg-slate-900 p-3 rounded text-left overflow-x-auto text-slate-400 font-mono">
              {code}
            </pre>
          </div>
        ) : svgContent ? (
          <div
            style={{ transform: `scale(${zoom})`, transformOrigin: "center center", transition: "transform 0.15s ease-out" }}
            // Mermaid-generated SVG only (securityLevel: "strict", tag/shape check above).
            dangerouslySetInnerHTML={{ __html: svgContent }}
            className="max-w-full"
          />
        ) : (
          <div className="text-xs text-slate-500">Rendering diagram…</div>
        )}
      </div>
    </div>
  );
}
