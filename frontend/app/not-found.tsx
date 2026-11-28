import Link from "next/link";
import { FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-background px-6 text-center text-foreground">
      <div className="mb-5 rounded-2xl border border-border bg-surface p-4 text-signal">
        <FileQuestion className="h-8 w-8" aria-hidden="true" />
      </div>
      <h1 className="mb-2 text-xl font-bold">Page not found</h1>
      <p className="mb-6 max-w-md text-sm text-muted-foreground">
        That route does not exist in the Research &amp; Visual Blog Studio. Head back to the studio workspace.
      </p>
      <Link
        href="/"
        className="rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-accent-foreground transition hover:bg-accent-hover"
      >
        Return to the studio
      </Link>
    </main>
  );
}
