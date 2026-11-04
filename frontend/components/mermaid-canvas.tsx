"use client";

import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { ZoomIn, ZoomOut, RotateCcw, Maximize2, Minimize2, Copy, Check, Download } from "lucide-react";

interface MermaidCanvasProps {
  code: string;
  title?: string;
}

export function MermaidCanvas({ code, title = "System Architecture Diagram" }: MermaidCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svgContent, setSvgContent] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number>(1);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    mermaid.initialize({
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
    });

    const renderDiagram = async () => {
      if (!code || !code.trim()) {
        setSvgContent("");
        return;
      }
      setError(null);
      try {
        const id = `mermaid_${Math.random().toString(36).substring(2, 9)}`;
        const { svg } = await mermaid.render(id, code.trim());
        setSvgContent(svg);
      } catch (err: any) {
        console.error("Mermaid render error:", err);
        setError("Could not render diagram syntax cleanly.");
      }
    };

    renderDiagram();
  }, [code]);

  const handleCopyCode = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadSvg = () => {
    if (!svgContent) return;
    const blob = new Blob([svgContent], { type: "image/svg+xml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `architecture_diagram.svg`;
    a.click();
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
          <span className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-pulse" />
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300">{title}</h4>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setZoom((z) => Math.min(z + 0.2, 2.5))}
            title="Zoom In"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <ZoomIn className="w-4 h-4" />
          </button>
          <button
            onClick={() => setZoom((z) => Math.max(z - 0.2, 0.5))}
            title="Zoom Out"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <ZoomOut className="w-4 h-4" />
          </button>
          <button
            onClick={() => setZoom(1)}
            title="Reset Zoom"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <RotateCcw className="w-4 h-4" />
          </button>
          <div className="w-px h-4 bg-slate-800 mx-1" />
          <button
            onClick={handleCopyCode}
            title="Copy Mermaid Code"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
          </button>
          <button
            onClick={handleDownloadSvg}
            title="Download SVG"
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            title={isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            className="p-1.5 hover:bg-slate-800 text-slate-400 hover:text-slate-200 rounded-lg transition"
          >
            {isFullscreen ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* SVG Container with pan & zoom scale */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto p-6 flex items-center justify-center min-h-[320px] select-none"
      >
        {error ? (
          <div className="text-center p-6 text-sm text-slate-400">
            <p className="text-amber-400 mb-2">{error}</p>
            <pre className="text-xs bg-slate-900 p-3 rounded text-left overflow-x-auto text-slate-400 font-mono">
              {code}
            </pre>
          </div>
        ) : (
          <div
            style={{ transform: `scale(${zoom})`, transformOrigin: "center center", transition: "transform 0.15s ease-out" }}
            dangerouslySetInnerHTML={{ __html: svgContent }}
            className="max-w-full"
          />
        )}
      </div>
    </div>
  );
}
