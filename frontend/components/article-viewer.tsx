"use client";

import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { MermaidCanvas } from "./mermaid-canvas";
import { Clock, BookOpen, Download, Copy, Check, FileText } from "lucide-react";

interface ArticleViewerProps {
  topic: string;
  content: string;
  wordCount?: number;
  generationTime?: number;
  onOpenCopilot?: () => void;
}

export function ArticleViewer({
  topic,
  content,
  wordCount,
  generationTime,
  onOpenCopilot,
}: ArticleViewerProps) {
  const [copied, setCopied] = React.useState(false);

  const calculatedWords = useMemo(() => {
    return wordCount || content.trim().split(/\s+/).filter(Boolean).length;
  }, [content, wordCount]);

  const readingTimeMin = useMemo(() => {
    return Math.max(1, Math.ceil(calculatedWords / 225));
  }, [calculatedWords]);

  // Extract H2 & H3 headings for floating Table of Contents
  const headings = useMemo(() => {
    const lines = content.split("\n");
    const list: Array<{ id: string; text: string; level: number }> = [];
    lines.forEach((line) => {
      const h2Match = line.match(/^##\s+(.+)$/);
      const h3Match = line.match(/^###\s+(.+)$/);
      if (h2Match) {
        const text = h2Match[1].trim();
        const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
        list.push({ id, text, level: 2 });
      } else if (h3Match) {
        const text = h3Match[1].trim();
        const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
        list.push({ id, text, level: 3 });
      }
    });
    return list;
  }, [content]);

  const handleCopyMarkdown = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${topic.toLowerCase().replace(/\s+/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="relative flex flex-col lg:flex-row gap-8 items-start w-full">
      {/* Main Content Column */}
      <div className="flex-1 min-w-0 bg-slate-900/60 border border-slate-800 rounded-3xl p-6 md:p-10 shadow-2xl backdrop-blur-sm">
        {/* Article Meta Bar */}
        <div className="border-b border-slate-800 pb-6 mb-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 rounded-full">
                <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
                {calculatedWords.toLocaleString()} words
              </span>
              <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-800 rounded-full">
                <Clock className="w-3.5 h-3.5 text-emerald-400" />
                {readingTimeMin} min read
              </span>
              {generationTime && (
                <span className="hidden sm:inline px-3 py-1 bg-slate-800 rounded-full text-slate-400">
                  Generated in {generationTime}s
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopyMarkdown}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? "Copied" : "Copy"}</span>
              </button>
              <button
                onClick={handleDownloadMarkdown}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-xl text-xs font-medium transition"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export .md</span>
              </button>
              {onOpenCopilot && (
                <button
                  onClick={onOpenCopilot}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-medium transition shadow-lg shadow-indigo-600/20"
                >
                  <FileText className="w-3.5 h-3.5" />
                  <span>AI Copilot</span>
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Markdown Prose Body */}
        <article className="prose prose-invert prose-indigo max-w-none prose-headings:font-bold prose-headings:tracking-tight prose-a:text-indigo-400 hover:prose-a:underline prose-pre:p-0 prose-pre:bg-transparent">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={{
              h2: ({ node, ...props }) => {
                const text = String(props.children);
                const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
                return <h2 id={id} className="scroll-mt-24 text-2xl font-bold mt-10 mb-4 pb-2 border-b border-slate-800/80 text-slate-100" {...props} />;
              },
              h3: ({ node, ...props }) => {
                const text = String(props.children);
                const id = text.toLowerCase().replace(/[^\w\s-]/g, "").replace(/\s+/g, "-");
                return <h3 id={id} className="scroll-mt-24 text-xl font-semibold mt-6 mb-3 text-slate-200" {...props} />;
              },
              code: ({ inline, className, children, ...props }: any) => {
                const match = /language-(\w+)/.exec(className || "");
                const isMermaid = match && match[1] === "mermaid";
                const codeString = String(children).replace(/\n$/, "");

                if (!inline && isMermaid) {
                  return <MermaidCanvas code={codeString} />;
                }

                if (!inline) {
                  return (
                    <div className="my-4 rounded-xl overflow-hidden border border-slate-800 bg-slate-950 p-4 font-mono text-sm">
                      <pre className="overflow-x-auto text-slate-300">
                        <code>{children}</code>
                      </pre>
                    </div>
                  );
                }

                return (
                  <code className="px-1.5 py-0.5 rounded-md bg-slate-800 text-indigo-300 font-mono text-xs" {...props}>
                    {children}
                  </code>
                );
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </article>
      </div>

      {/* Floating Sticky Table of Contents (Desktop) */}
      {headings.length > 0 && (
        <aside className="hidden xl:block w-72 shrink-0 sticky top-8 p-6 bg-slate-900/50 border border-slate-800/80 rounded-2xl backdrop-blur-sm">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
            Table of Contents
          </h4>
          <nav className="space-y-2 text-xs">
            {headings.map((h, i) => (
              <a
                key={i}
                href={`#${h.id}`}
                className={`block transition-colors line-clamp-1 ${
                  h.level === 3 ? "pl-3 text-slate-500 hover:text-slate-300" : "text-slate-400 hover:text-indigo-400 font-medium"
                }`}
              >
                {h.text}
              </a>
            ))}
          </nav>
        </aside>
      )}
    </div>
  );
}
