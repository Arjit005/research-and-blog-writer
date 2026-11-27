"use client";

import { useEffect, useState } from "react";
import { Code2, Download, Eye } from "lucide-react";

interface D2CanvasProps {
  code: string;
  title?: string;
  caption?: string;
  className?: string;
}

export function D2Canvas({
  code,
  title = "Research diagram",
  caption,
  className = "my-8",
}: D2CanvasProps) {
  const [svgUrl, setSvgUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSource, setShowSource] = useState(false);

  // Some model output uses `storage` as a generic shape name, which D2 does not
  // support. Render it as the closest valid built-in shape without rewriting the
  // preserved source shown to the user.
  const renderableCode = code.replace(
    /(\bshape\s*:\s*)["']?storage["']?/gi,
    "$1cylinder"
  );

  useEffect(() => {
    let disposed = false;
    let timedOut = false;
    let objectUrl: string | null = null;
    let d2Instance: import("@d2lang/d2").D2 | null = null;
    let timeoutId: number | undefined;

    setSvgUrl(null);
    setError(null);

    const render = async () => {
      try {
        if (code.length > 20_000) {
          throw new Error("This diagram is too large to render. Keep diagrams under 20,000 characters.");
        }
        const { D2 } = await import("@d2lang/d2");
        if (disposed) return;
        d2Instance = new D2();
        timeoutId = window.setTimeout(() => {
          timedOut = true;
          void d2Instance?.dispose();
          if (!disposed) setError("Rendering took too long. Try simplifying or splitting this diagram.");
        }, 15_000);
        const result = await d2Instance.compile(renderableCode, { layout: "tala", darkThemeID: 200 });
        if (disposed || timedOut) return;
        const svg = await d2Instance.render(result.diagram, {
          ...result.renderOptions,
          center: true,
          pad: 32,
          darkThemeID: 200,
          noXMLTag: true,
        });
        if (disposed || timedOut) return;

        objectUrl = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        setSvgUrl(objectUrl);
      } catch (renderError) {
        if (!disposed && !timedOut) {
          setError(renderError instanceof Error ? renderError.message : "Could not render this D2 diagram.");
        }
      } finally {
        if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      }
    };

    void render();
    return () => {
      disposed = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      if (d2Instance) void d2Instance.dispose();
    };
  }, [code]);

  return (
    <figure className={`${className} overflow-hidden rounded-2xl border border-border bg-surface shadow-xl`}>
      <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-raised px-4 py-3">
        <h3 className="truncate text-xs font-semibold uppercase tracking-wider text-foreground">{title}</h3>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            onClick={() => setShowSource((visible) => !visible)}
            className="rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-surface"
            aria-label={showSource ? "View rendered D2 diagram" : "View D2 source"}
          >
            {showSource ? <Eye className="h-4 w-4" aria-hidden="true" /> : <Code2 className="h-4 w-4" aria-hidden="true" />}
          </button>
          <a
            href={svgUrl ?? undefined}
            download={`${title.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "diagram"}.svg`}
            aria-disabled={!svgUrl || showSource}
            tabIndex={!svgUrl || showSource ? -1 : 0}
            className={`rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-surface ${!svgUrl || showSource ? "pointer-events-none opacity-40" : ""}`}
            aria-label="Download diagram as SVG"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
          </a>
        </div>
      </div>

      <div className="flex min-h-[280px] max-h-[640px] items-center justify-center overflow-auto p-6">
        {showSource ? (
          <pre className="max-h-[560px] w-full overflow-auto whitespace-pre-wrap rounded-xl bg-surface-raised p-4 font-mono text-xs text-foreground">
            <code>{code}</code>
          </pre>
        ) : error ? (
          <div className="w-full rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 text-sm text-foreground">
            <p className="font-semibold">D2 could not render this diagram</p>
            <p className="mt-2 break-words text-xs text-muted-foreground">{error}</p>
            <pre className="mt-4 max-h-48 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-raised p-3 font-mono text-xs">
              <code>{code}</code>
            </pre>
          </div>
        ) : svgUrl ? (
          <img src={svgUrl} alt={title} className="max-h-[560px] max-w-full object-contain" />
        ) : (
          <p className="text-xs text-muted-foreground" role="status">Rendering diagram…</p>
        )}
      </div>

      {caption && <figcaption className="border-t border-border px-5 py-3 text-xs text-muted-foreground">{caption}</figcaption>}
    </figure>
  );
}
