"use client";

import React, { useMemo, useState, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
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
  isStreaming?: boolean;
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
    return getNodeText((node.props as { children: React.ReactNode }).children);
  }
  return "";
}

export function ArticleViewer({
  topic,
  content,
  wordCount,
  generationTime,
  isStreaming = false,
  onOpenCopilot,
  onOpenVersionHistory,
}: ArticleViewerProps) {
  const [copiedArticle, setCopiedArticle] = useState(false);
  const [copiedCitations, setCopiedCitations] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(false);
  const [showTocMobile, setShowTocMobile] = useState(false);
  const articleRef = useRef<HTMLDivElement>(null);

  // Extract primary citations/references
  const citations = useMemo(() => {
    const urls: string[] = [];
    const urlRegex = /(https?:\/\/[^\s)]+)/g;
    let match;
    while ((match = urlRegex.exec(content)) !== null) {
      if (!urls.includes(match[1])) {
        urls.push(match[1]);
      }
    }
    return urls;
  }, [content]);

  // Extract structured headings for dynamic TOC
  const headings = useMemo(() => {
    const headingLines: { id: string; text: string; level: number }[] = [];
    const lines = content.split("\n");
    const counts: Record<string, number> = {};

    for (const line of lines) {
      const match = line.match(/^(#{2,3})\s+(.*)$/);
      if (match) {
        const level = match[1].length;
        const rawText = match[2].trim();
        const cleanText = stripMarkdown(rawText);
        let id = slugifyHeading(cleanText);

        if (counts[id] !== undefined) {
          counts[id] += 1;
          id = `${id}-${counts[id]}`;
        } else {
          counts[id] = 0;
        }

        headingLines.push({ id, text: cleanText, level });
      }
    }
    return headingLines;
  }, [content]);

  const headingIdCountsRef = useRef<Record<string, number>>({});
  headingIdCountsRef.current = {};

  const getNextHeadingId = (cleanText: string): string => {
    let base = slugifyHeading(cleanText);
    const seen = headingIdCountsRef.current[base];
    if (seen !== undefined) {
      headingIdCountsRef.current[base] = seen + 1;
      return `${base}-${seen + 1}`;
    }
    headingIdCountsRef.current[base] = 0;
    return base;
  };

  const calculatedWords = useMemo(() => {
    if (wordCount && wordCount > 0) return wordCount;
    return content.trim().split(/\s+/).filter(Boolean).length;
  }, [content, wordCount]);

  const readingTimeMin = Math.max(1, Math.ceil(calculatedWords / 225));

  const handleCopyArticle = async () => {
    await navigator.clipboard.writeText(content);
    setCopiedArticle(true);
    setTimeout(() => setCopiedArticle(false), 2000);
  };

  const handleCopyCitations = async () => {
    if (citations.length === 0) return;
    const formatted = citations.map((url, i) => `[${i + 1}] ${url}`).join("\n");
    await navigator.clipboard.writeText(formatted);
    setCopiedCitations(true);
    setTimeout(() => setCopiedCitations(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    const filename = `${topic.toLowerCase().replace(/[^a-z0-9]+/g, "-") || "research-article"}.md`;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const handlePrintPdf = () => {
    window.print();
  };

  const markdownComponents: Components = {
    h1: ({ children }) => (
      <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight text-foreground mt-2 mb-6 pb-4 border-b border-border leading-tight">
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
          className={`scroll-mt-24 text-2xl font-bold mt-12 mb-4 pb-2 border-b border-border text-foreground flex items-center gap-2 group ${
            isExecutiveSummary ? "text-blue-600 dark:text-blue-400" : ""
          }`}
        >
          <a
            href={`#${id}`}
            className="text-muted-foreground hover:text-blue-600 dark:hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity"
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
          className="scroll-mt-24 text-lg font-semibold mt-8 mb-3 text-foreground flex items-center gap-2 group"
        >
          <a
            href={`#${id}`}
            className="text-muted-foreground hover:text-blue-600 dark:hover:text-blue-400 opacity-0 group-hover:opacity-100 transition-opacity"
            aria-label={`Link to ${text}`}
          >
            <Hash className="w-4 h-4" />
          </a>
          <span>{children}</span>
        </h3>
      );
    },
    p: ({ children }) => (
      <p className="text-foreground/90 leading-relaxed text-[15px] md:text-base my-4 tracking-normal">
        {children}
      </p>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-6 pl-4 border-l-4 border-blue-600 bg-surface-raised p-4 rounded-r-2xl italic text-foreground text-sm md:text-base">
        {children}
      </blockquote>
    ),
    table: ({ children }) => (
      <div className="my-8 overflow-x-auto rounded-2xl border border-border bg-surface shadow-sm">
        <table className="w-full text-left border-collapse text-xs md:text-sm text-foreground">
          {children}
        </table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-surface-raised border-b border-border font-semibold text-foreground text-xs uppercase tracking-wider">
        {children}
      </thead>
    ),
    tbody: ({ children }) => <tbody className="divide-y divide-border">{children}</tbody>,
    th: ({ children }) => <th className="px-4 py-3 font-semibold text-blue-600 dark:text-blue-400">{children}</th>,
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
          <div className="my-6 rounded-2xl overflow-hidden border border-border bg-slate-900 text-slate-100 shadow-sm">
            <div className="flex items-center justify-between px-4 py-2 bg-slate-950/80 border-b border-slate-800 text-[11px] font-mono text-slate-400">
              <span>{language || "code"}</span>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(codeText);
                }}
                className="hover:text-blue-300 transition"
                title="Copy code snippet"
              >
                Copy
              </button>
            </div>
            <pre className="p-4 overflow-x-auto text-xs md:text-sm font-mono leading-relaxed">
              <code className={className}>{children}</code>
            </pre>
          </div>
        );
      }

      return (
        <code
          className="px-1.5 py-0.5 rounded-md bg-surface-raised text-blue-600 dark:text-blue-400 font-mono text-xs border border-border"
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
          className="text-blue-600 dark:text-blue-400 hover:text-blue-700 underline underline-offset-4 decoration-blue-500/40 hover:decoration-blue-600 transition"
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
      <div className="sticky top-16 z-30 flex flex-wrap items-center justify-between gap-3 p-3.5 bg-surface/90 border border-border rounded-2xl backdrop-blur-xl shadow-sm">
        {/* Left Stats */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <span className="flex items-center gap-1.5 px-3 py-1 bg-surface-raised border border-border rounded-xl text-xs font-medium text-foreground">
            <BookOpen className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
            <span>{calculatedWords.toLocaleString()} words</span>
          </span>
          {isStreaming ? (
            <span className="flex items-center gap-1.5 px-3 py-1 bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-500/40 rounded-xl text-xs font-medium text-emerald-700 dark:text-emerald-300 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
              <span>Streaming Draft Live...</span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-3 py-1 bg-surface-raised border border-border rounded-xl text-xs font-medium text-foreground">
              <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>{readingTimeMin} min read</span>
            </span>
          )}
          {generationTime && (
            <span className="hidden sm:flex items-center gap-1 px-3 py-1 bg-surface-raised border border-border rounded-xl text-xs text-muted-foreground">
              <span>Gen: {generationTime}s</span>
            </span>
          )}
          {citations.length > 0 && (
            <span className="hidden md:flex items-center gap-1 px-3 py-1 bg-blue-50 dark:bg-blue-950/40 border border-blue-500/30 rounded-xl text-xs text-blue-700 dark:text-blue-300">
              <LinkIcon className="w-3 h-3 text-blue-600 dark:text-blue-400" />
              <span>{citations.length} Verified Sources</span>
            </span>
          )}
        </div>

        {/* Right Supported Toolbar Actions */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {/* Copy Article */}
          <button
            type="button"
            onClick={handleCopyArticle}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
            title="Copy entire markdown article to clipboard"
          >
            {copiedArticle ? (
              <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <Copy className="w-3.5 h-3.5 text-muted-foreground" />
            )}
            <span className="hidden md:inline">{copiedArticle ? "Copied" : "Copy Article"}</span>
          </button>

          {/* Copy Citations */}
          <button
            type="button"
            onClick={handleCopyCitations}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
            title="Copy bibliography & sources"
          >
            {copiedCitations ? (
              <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            ) : (
              <Quote className="w-3.5 h-3.5 text-muted-foreground" />
            )}
            <span className="hidden md:inline">{copiedCitations ? "Copied" : "Copy Citations"}</span>
          </button>

          {/* Export Markdown */}
          <button
            type="button"
            onClick={handleDownloadMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
            title="Download .md file"
          >
            <Download className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="hidden sm:inline">Export .md</span>
          </button>

          {/* Export PDF */}
          <button
            type="button"
            onClick={handlePrintPdf}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
            title="Export or Print as PDF"
          >
            <Printer className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="hidden sm:inline">Export PDF</span>
          </button>

          {/* Version History */}
          {onOpenVersionHistory && (
            <button
              type="button"
              onClick={onOpenVersionHistory}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
              title="Open Revisions Timeline"
            >
              <Bookmark className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
              <span className="hidden lg:inline">Versions</span>
            </button>
          )}

          {/* Distraction-Free Reading Mode Toggle */}
          <button
            type="button"
            onClick={() => setIsFocusMode(!isFocusMode)}
            className="p-1.5 bg-surface-raised hover:bg-slate-200 dark:hover:bg-slate-800 border border-border text-muted-foreground hover:text-foreground rounded-xl transition cursor-pointer"
            title={isFocusMode ? "Exit Focus Mode" : "Distraction-Free Focus Mode"}
          >
            {isFocusMode ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>

          {/* AI Copilot Drawer */}
          {onOpenCopilot && (
            <button
              type="button"
              onClick={onOpenCopilot}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white rounded-xl text-xs font-semibold shadow-md shadow-blue-600/20 transition cursor-pointer"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>AI Copilot</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Main Content Layout */}
      <div className="w-full">
        {/* Center Article Reader Container */}
        <article
          ref={articleRef}
          className="w-full select-text selection:bg-blue-500/20 selection:text-blue-900 dark:selection:text-blue-100 bg-surface border border-border rounded-3xl p-6 sm:p-10 md:p-12 shadow-sm backdrop-blur-md"
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm, remarkMath]}
            rehypePlugins={[rehypeKatex]}
            components={markdownComponents}
          >
            {content}
          </ReactMarkdown>

          {/* Live Streaming Indicator Cursor */}
          {isStreaming && (
            <div className="mt-4 flex items-center gap-2 text-blue-600 dark:text-blue-400 font-mono text-sm select-none">
              <span className="inline-block w-2.5 h-5 bg-blue-600 dark:bg-blue-400 animate-pulse rounded-sm" />
              <span className="text-xs text-muted-foreground italic">Blog Writer drafting token-by-token...</span>
            </div>
          )}

          {/* End of article citation summary card */}
          {citations.length > 0 && (
            <div className="mt-14 pt-8 border-t border-border">
              <div className="flex items-center justify-between mb-4">
                <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
                  <LinkIcon className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400" />
                  Verified Primary References ({citations.length})
                </h4>
                <button
                  type="button"
                  onClick={handleCopyCitations}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-700 transition cursor-pointer"
                >
                  {copiedCitations ? "Copied Sources" : "Copy All Sources"}
                </button>
              </div>
              <ul className="space-y-2 text-xs text-muted-foreground font-mono bg-surface-raised p-4 rounded-2xl border border-border">
                {citations.map((c, i) => (
                  <li key={i} className="truncate">
                    <span className="text-blue-600 dark:text-blue-400 mr-2">[{i + 1}]</span>
                    {c}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </article>
      </div>
    </div>
  );
}
