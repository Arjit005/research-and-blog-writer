"use client";

import React, { useMemo, useState, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { MermaidCanvas } from "./mermaid-canvas";
import {
  Clock,
  BookOpen,
  Download,
  Copy,
  Check,
  FileText,
  Printer,
  Maximize2,
  Minimize2,
  Hash,
    Bookmark,
  Quote,
    Link as LinkIcon,
    ListOrdered,
} from "lucide-react";

interface ArticleViewerProps {
  topic: string;
  content: string;
  wordCount?: number;
  generationTime?: number;
  onOpenCopilot?: () => void;
  onOpenVersionHistory?: () => void;
}

function stripMarkdown(text: string): string {
  return text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[*_~`#]/g, "")
    .replace(/<[^>]+>/g, "")
    .trim();
}

function slugifyHeading(text: string): string {
  const stripped = stripMarkdown(text);
  const slug = stripped
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/\s+/g, "-");
  return slug || "heading";
}

function getNodeText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(getNodeText).join("");
  }
  if (React.isValidElement(node) && (node.props as { children?: React.ReactNode })?.children) {
    return getNodeText((node.props as { children?: React.ReactNode }).children);
  }
  return "";
}

export function ArticleViewer({
  topic,
  content,
  wordCount,
  generationTime,
  onOpenCopilot,
  onOpenVersionHistory,
}: ArticleViewerProps) {
  const [copiedArticle, setCopiedArticle] = useState(false);
  const [copiedCitations, setCopiedCitations] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(false);
  const [showTocMobile, setShowTocMobile] = useState(false);
  const articleRef = useRef<HTMLElement>(null);

  const calculatedWords = useMemo(() => {
    return wordCount || content.trim().split(/\s+/).filter(Boolean).length;
  }, [content, wordCount]);

  const readingTimeMin = useMemo(() => {
    return Math.max(1, Math.ceil(calculatedWords / 225));
  }, [calculatedWords]);

  // Extract H2 & H3 headings for dynamic Table of Contents with unique IDs
  const headings = useMemo(() => {
    const lines = content.split("\n");
    const list: Array<{ id: string; text: string; level: number }> = [];
    const seenIds: Record<string, number> = {};

    lines.forEach((line) => {
      const h2Match = line.match(/^##\s+(.+)$/);
      const h3Match = line.match(/^###\s+(.+)$/);
      if (h2Match || h3Match) {
        const rawText = (h2Match ? h2Match[1] : (h3Match ? h3Match[1] : "")).trim();
        const cleanText = stripMarkdown(rawText);
        const baseId = slugifyHeading(cleanText);
        const count = seenIds[baseId] || 0;
        seenIds[baseId] = count + 1;
        const uniqueId = count === 0 ? baseId : `${baseId}-${count}`;
        list.push({
          id: uniqueId,
          text: cleanText,
          level: h2Match ? 2 : 3,
        });
      }
    });
    return list;
  }, [content]);

  // Group occurrences of each heading in exact document order
  const headingOccurrences = useMemo(() => {
    const map = new Map<string, string[]>();
    headings.forEach((h) => {
      const existing = map.get(h.text) || [];
      existing.push(h.id);
      map.set(h.text, existing);
    });
    return map;
  }, [headings]);

  // Generator for heading IDs that resets at the start of each render pass
  const headingCounts = useMemo<Record<string, number>>(() => ({}), [content]);
  const getNextHeadingId = (text: string) => {
    const index = headingCounts[text] || 0;
    headingCounts[text] = index + 1;
    const ids = headingOccurrences.get(text);
    if (ids && index < ids.length) {
      return ids[index];
    }
    return slugifyHeading(text);
  };

  // Extract citations/references list from content
  const citations = useMemo(() => {
    const list: string[] = [];
    // Matches markdown links [Title](http...) or reference entries
    const regex = /\[(\d+|[^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
    let match;
    while ((match = regex.exec(content)) !== null) {
      list.push(`${match[1]}: ${match[2]}`);
    }
    // Also look for numbered list under References section
    const refSection = content.split(/##\s+References|##\s+Verified Sources/i)[1];
    if (refSection) {
      const refLines = refSection
        .split("\n")
        .filter((l) => /^(\d+\.|-|\*|\[)/.test(l.trim()));
      refLines.forEach((rl) => {
        const trimmed = rl.trim();
        if (!list.includes(trimmed) && trimmed.length > 3) {
          list.push(trimmed);
        }
      });
    }
    return Array.from(new Set(list));
  }, [content]);

  // Actions
  const handleCopyArticle = () => {
    void navigator.clipboard.writeText(content).catch((err: unknown) => {
      console.error("Clipboard write failed:", err);
    });
    setCopiedArticle(true);
    setTimeout(() => setCopiedArticle(false), 2000);
  };

  const handleCopyCitations = () => {
    const textToCopy =
      citations.length > 0
        ? citations.join("\n")
        : "No explicit citations found in this article.";
    void navigator.clipboard.writeText(textToCopy).catch((err: unknown) => {
      console.error("Clipboard write failed:", err);
    });
    setCopiedCitations(true);
    setTimeout(() => setCopiedCitations(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${topic.toLowerCase().replace(/[^a-z0-9]+/g, "_")}.md`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handlePrintPdf = () => {
    window.print();
  };

  /**
   * Custom Markdown Components adhering to Notion/Linear aesthetic:
   * Executive summaries highlighted, readable tables, clean code blocks,
   * proper section hierarchy, and interactive Mermaid diagrams.
   */
  const markdownComponents: Components = {
    h1: ({ children }) => (
      <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-slate-100 mt-2 mb-6 pb-4 border-b border-slate-800/80 leading-tight">
        {children}
      </h1>
    ),
    h2: ({ children }) => {
      const text = getNodeText(children);
      const id = getNextHeadingId(text);
      const isExecutiveSummary = /executive\s+summary/i.test(text);
      return (
        <h2
          id={id}
          className={`scroll-mt-24 text-2xl font-bold mt-12 mb-4 pb-2 border-b border-slate-800/80 text-slate-100 flex items-center gap-2 group ${
            isExecutiveSummary ? "text-indigo-400" : ""
          }`}
        >
          <a
            href={`#${id}`}
            className="text-slate-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity"
            aria-label={`Link to ${text}`}
          >
            <Hash className="w-5 h-5" />
          </a>
          <span>{children}</span>
        </h2>
      );
    },
    h3: ({ children }) => {
      const text = getNodeText(children);
      const id = getNextHeadingId(text);
      return (
        <h3
          id={id}
          className="scroll-mt-24 text-lg font-semibold mt-8 mb-3 text-slate-200 flex items-center gap-2 group"
        >
          <a
            href={`#${id}`}
            className="text-slate-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-opacity"
            aria-label={`Link to ${text}`}
          >
            <Hash className="w-4 h-4" />
          </a>
          <span>{children}</span>
        </h3>
      );
    },
    p: ({ children }) => (
      <p className="text-slate-300 leading-relaxed text-[15px] md:text-base my-4 tracking-normal">
        {children}
      </p>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-6 pl-4 border-l-4 border-indigo-500 bg-slate-900/60 p-4 rounded-r-2xl italic text-slate-300 text-sm md:text-base">
        {children}
      </blockquote>
    ),
    table: ({ children }) => (
      <div className="my-8 overflow-x-auto rounded-2xl border border-slate-800 bg-slate-950/90 shadow-xl">
        <table className="w-full text-left border-collapse text-xs md:text-sm text-slate-300">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-slate-900 border-b border-slate-800 font-semibold text-slate-200 text-xs uppercase tracking-wider">
        {children}
      </thead>
    ),
    tbody: ({ children }) => <tbody className="divide-y divide-slate-800/60">{children}</tbody>,
    th: ({ children }) => <th className="px-4 py-3 font-semibold text-indigo-300">{children}</th>,
    td: ({ children }) => <td className="px-4 py-3 leading-normal">{children}</td>,
    pre: ({ children }) => <>{children}</>,
    code: ({ className, children, ...props }) => {
      const languageMatch = /language-(\w+)/.exec(className ?? "");
      const language = languageMatch?.[1];
      const rawText = String(children);
      const isBlock = Boolean(language) || rawText.includes("\n");
      const codeText = rawText.replace(/\n$/, "");

      if (isBlock && language === "mermaid") {
        return <MermaidCanvas code={codeText} />;
      }

      if (isBlock) {
        return (
          <div className="my-6 rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-lg">
            <div className="flex items-center justify-between px-4 py-2 bg-slate-900/70 border-b border-slate-800 text-[11px] font-mono text-slate-400">
              <span>{language || "code"}</span>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(codeText);
                }}
                className="hover:text-indigo-300 transition"
                title="Copy code snippet"
              >
                Copy
              </button>
            </div>
            <pre className="p-4 overflow-x-auto text-xs md:text-sm font-mono text-slate-300 leading-relaxed">
              <code className={className}>{children}</code>
            </pre>
          </div>
        );
      }

      return (
        <code
          className="px-1.5 py-0.5 rounded-md bg-slate-800/80 text-indigo-300 font-mono text-xs border border-slate-700/50"
          {...props}
        >
          {children}
        </code>
      );
    },
    a: ({ href, children }) => {
      const isInternal = href?.startsWith("#");
      return (
        <a
          href={href}
          target={isInternal ? undefined : "_blank"}
          rel={isInternal ? undefined : "noopener noreferrer"}
          className="text-indigo-400 hover:text-indigo-300 underline underline-offset-4 decoration-indigo-500/40 hover:decoration-indigo-400 transition"
        >
          {children}
        </a>
      );
    },
  };

  return (
    <div
      className={`relative w-full flex flex-col gap-6 transition-all ${
        isFocusMode ? "max-w-5xl mx-auto" : "max-w-full"
      }`}
    >
      {/* 1. Article Actions Bar */}
      <div className="sticky top-16 z-30 flex flex-wrap items-center justify-between gap-3 p-3.5 bg-slate-950/80 border border-slate-800/80 rounded-2xl backdrop-blur-xl shadow-lg">
        {/* Left Stats */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-900 border border-slate-800/80 rounded-xl text-xs font-medium text-slate-300">
            <BookOpen className="w-3.5 h-3.5 text-indigo-400" />
            <span>{calculatedWords.toLocaleString()} words</span>
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1 bg-slate-900 border border-slate-800/80 rounded-xl text-xs font-medium text-slate-300">
            <Clock className="w-3.5 h-3.5 text-emerald-400" />
            <span>{readingTimeMin} min read</span>
          </span>
          {generationTime && (
            <span className="hidden sm:flex items-center gap-1 px-3 py-1 bg-slate-900/60 border border-slate-800/50 rounded-xl text-xs text-slate-400">
              <span>Gen: {generationTime}s</span>
            </span>
          )}
          {citations.length > 0 && (
            <span className="hidden md:flex items-center gap-1 px-3 py-1 bg-indigo-950/40 border border-indigo-500/30 rounded-xl text-xs text-indigo-300">
              <LinkIcon className="w-3 h-3 text-indigo-400" />
              <span>{citations.length} Verified Sources</span>
            </span>
          )}
        </div>

        {/* Right Supported Toolbar Actions */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Mobile TOC Button */}
          {headings.length > 0 && (
            <button
              type="button"
              onClick={() => setShowTocMobile(!showTocMobile)}
              className="xl:hidden flex items-center gap-1 px-2.5 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs transition"
              title="Table of Contents"
            >
              <ListOrdered className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden sm:inline">TOC</span>
            </button>
          )}

          {/* Copy Article */}
          <button
            type="button"
            onClick={handleCopyArticle}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition"
            title="Copy entire markdown article to clipboard"
          >
            {copiedArticle ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span className="hidden md:inline">{copiedArticle ? "Copied" : "Copy Article"}</span>
          </button>

          {/* Copy Citations */}
          <button
            type="button"
            onClick={handleCopyCitations}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition"
            title="Copy bibliography & sources"
          >
            {copiedCitations ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Quote className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span className="hidden md:inline">{copiedCitations ? "Copied" : "Copy Citations"}</span>
          </button>

          {/* Export Markdown */}
          <button
            type="button"
            onClick={handleDownloadMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition"
            title="Download .md file"
          >
            <Download className="w-3.5 h-3.5 text-slate-400" />
            <span className="hidden sm:inline">Export .md</span>
          </button>

          {/* Export PDF (Browser Native High-Fidelity Print) */}
          <button
            type="button"
            onClick={handlePrintPdf}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition"
            title="Export or Print as PDF"
          >
            <Printer className="w-3.5 h-3.5 text-slate-400" />
            <span className="hidden sm:inline">Export PDF</span>
          </button>

          {/* Version History (if handler available) */}
          {onOpenVersionHistory && (
            <button
              type="button"
              onClick={onOpenVersionHistory}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300 rounded-xl text-xs font-medium transition"
              title="Open Revisions Timeline"
            >
              <Bookmark className="w-3.5 h-3.5 text-indigo-400" />
              <span className="hidden lg:inline">Versions</span>
            </button>
          )}

          {/* Distraction-Free Reading Mode Toggle */}
          <button
            type="button"
            onClick={() => setIsFocusMode(!isFocusMode)}
            className="p-1.5 bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-400 hover:text-slate-200 rounded-xl transition"
            title={isFocusMode ? "Exit Focus Mode" : "Distraction-Free Focus Mode"}
          >
            {isFocusMode ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>

          {/* AI Copilot Drawer */}
          {onOpenCopilot && (
            <button
              type="button"
              onClick={onOpenCopilot}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white rounded-xl text-xs font-semibold shadow-md shadow-indigo-600/20 transition"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>AI Copilot</span>
            </button>
          )}
        </div>
      </div>

      {/* Mobile TOC Drawer dropdown */}
      {showTocMobile && headings.length > 0 && (
        <div className="xl:hidden p-4 bg-slate-900 border border-slate-800 rounded-2xl shadow-xl">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-2">
            Table of Contents
          </h4>
          <nav className="space-y-1.5 max-h-48 overflow-y-auto text-xs">
            {headings.map((h, i) => (
              <a
                key={i}
                href={`#${h.id}`}
                onClick={() => setShowTocMobile(false)}
                className={`block py-1 text-slate-300 hover:text-indigo-400 ${
                  h.level === 3 ? "pl-3 text-slate-400" : "font-medium"
                }`}
              >
                {h.text}
              </a>
            ))}
          </nav>
        </div>
      )}

      {/* 2. Main Content & Sticky TOC Layout */}
      <div className="flex gap-8 items-start w-full">
        {/* Center Article Reader Container */}
        <article
          ref={articleRef}
          className="flex-1 min-w-0 bg-slate-900/60 border border-slate-800/80 rounded-3xl p-6 sm:p-10 md:p-14 shadow-2xl backdrop-blur-md"
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeSanitize]}
            components={markdownComponents}
          >
            {content}
          </ReactMarkdown>

          {/* End of article citation summary card */}
          {citations.length > 0 && (
            <div className="mt-14 pt-8 border-t border-slate-800/80">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <LinkIcon className="w-3.5 h-3.5 text-indigo-400" />
                  Verified Primary References ({citations.length})
                </h4>
                <button
                  type="button"
                  onClick={handleCopyCitations}
                  className="text-xs text-indigo-400 hover:text-indigo-300 transition"
                >
                  {copiedCitations ? "Copied Sources" : "Copy All Sources"}
                </button>
              </div>
              <ul className="space-y-2 text-xs text-slate-400 font-mono bg-slate-950/70 p-4 rounded-2xl border border-slate-800/70">
                {citations.map((c, i) => (
                  <li key={i} className="truncate">
                    <span className="text-indigo-400 mr-2">[{i + 1}]</span>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </article>

        {/* 3. Floating Sticky Table of Contents (Desktop XL+) */}
        {!isFocusMode && headings.length > 0 && (
          <aside className="hidden xl:block w-72 shrink-0 sticky top-36 p-5 bg-slate-900/50 border border-slate-800/80 rounded-2xl backdrop-blur-md max-h-[calc(100vh-160px)] overflow-y-auto">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-300 mb-3 pb-2 border-b border-slate-800/70">
              <ListOrdered className="w-3.5 h-3.5 text-indigo-400" />
              <span>Outline</span>
            </div>
            <nav className="space-y-2 text-xs" aria-label="Table of contents">
              {headings.map((heading, idx) => (
                <a
                  key={idx}
                  href={`#${heading.id}`}
                  className={`block transition-colors line-clamp-1 py-0.5 ${
                    heading.level === 3
                      ? "pl-3 text-slate-400 hover:text-slate-200 text-[11px]"
                      : "text-slate-300 hover:text-indigo-400 font-medium"
                  }`}
                >
                  {heading.text}
                </a>
              ))}
            </nav>
          </aside>
        )}
      </div>
    </div>
  );
}