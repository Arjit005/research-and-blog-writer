import Link from "next/link";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center text-slate-100">
      <div className="mb-5 rounded-2xl border border-slate-800 bg-slate-900 p-4 text-indigo-400">
        <FileQuestion className="h-8 w-8" aria-hidden="true" />
      </div>
      <h1 className="mb-2 text-xl font-bold">Page not found</h1>
      <p className="mb-6 max-w-md text-sm text-slate-400">
        That route does not exist in the Research &amp; Visual Blog Studio. Head back to the studio workspace.
      </p>
      <Link
        href="/"
        className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500"
      >
        Return to the studio
      </Link>
    </main>
  );
}
