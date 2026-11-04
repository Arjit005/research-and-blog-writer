"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";

/**
 * Route-level error boundary.
 *
 * Next.js 16 passes both `retry` (stable since v16.3, refreshes the segment)
 * and `reset` (clears the boundary without re-fetching).
 */
export default function Error({
  error,
  retry,
  reset,
}: {
  error: unknown;
  retry?: () => void;
  reset?: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled UI error:", error);
  }, [error]);

  const recover = retry ?? reset;
  const digest = error instanceof Error && "digest" in error ? String(error.digest) : null;

  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center text-slate-100">
      <div className="mb-5 rounded-2xl border border-rose-500/30 bg-rose-500/10 p-4 text-rose-300">
        <AlertTriangle className="h-8 w-8" aria-hidden="true" />
      </div>
      <h1 className="mb-2 text-xl font-bold">Something went wrong</h1>
      <p className="mb-6 max-w-md text-sm text-slate-400">
        The studio UI hit an unexpected error. You can retry rendering this page; your research runs and revisions are
        stored server-side.
      </p>
      {digest && <p className="mb-6 font-mono text-[11px] text-slate-600">Reference: {digest}</p>}
      {recover && (
        <button
          type="button"
          onClick={recover}
          className="flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Try again
        </button>
      )}
    </main>
  );
}
