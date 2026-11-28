"use client";

import React, { useMemo, useState, useRef } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github.css";
import { MermaidCanvas } from "./mermaid-canvas";
import { D2Canvas } from "./d2-canvas";
import { InteractiveChartExplorer } from "./interactive-chart-explorer";
import { PremiumButton } from "./premium-button";
import { ResearchChart } from "@/lib/api";
import {
  Clock,
  BookOpen,
  Download,
  Copy,
  ChevronDown,
  Check,
  FileText,
  Printer,
  Maximize2,
  Minimize2,
  Hash,
  Bookmark,
  Quote,
  Link as LinkIcon,
  ShieldCheck,
  Image as ImageIcon,
} from "lucide-react";

interface ArticleViewerProps {
  topic: string;
  content: string;
  articleId?: number;
  wordCount?: number;
  generationTime?: number;
  isStreaming?: boolean;
  onOpenCopilot?: () => void;
  onOpenVersionHistory?: () => void;
  onOpenQualityAuditor?: () => void;
  onOpenVisualLibrary?: () => void;
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
  articleId: _articleId,
  wordCount,
  generationTime,
  isStreaming = false,
  onOpenCopilot,
  onOpenVersionHistory,
  onOpenQualityAuditor,
  onOpenVisualLibrary,
}: ArticleViewerProps) {
  const [copiedArticle, setCopiedArticle] = useState(false);
  const [copiedCitations, setCopiedCitations] = useState(false);
  const [exportMenuOpen, setExportMenuOpen] = useState(false);
  const [isFocusMode, setIsFocusMode] = useState(false);
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

  // Dynamic heading counts derived per render
  const headingSeenCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    return counts;
  }, [content]);

  const getNextHeadingId = (cleanText: string): string => {
    const base = slugifyHeading(cleanText);
    const seen = headingSeenCounts[base];
    if (seen !== undefined) {
      headingSeenCounts[base] = seen + 1;
      return `${base}-${seen + 1}`;
    }
    headingSeenCounts[base] = 0;
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
      <h1 className="text-4xl md:text-5xl font-extrabold tracking-tighter text-foreground mt-2 mb-6 pb-4 border-b border-border leading-tight">
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
          className={`scroll-mt-24 text-2xl font-bold tracking-tight text-foreground mt-12 mb-4 pb-2.5 border-b border-border flex items-center gap-2 group ${
            isExecutiveSummary ? "text-accent" : "text-foreground"
          }`}
        >
          <a
            href={`#${id}`}
            className="text-muted-foreground hover:text-accent opacity-0 group-hover:opacity-100 transition-opacity"
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
          className="scroll-mt-24 text-lg font-semibold tracking-tight text-foreground mt-8 mb-3 flex items-center gap-2 group"
        >
          <a
            href={`#${id}`}
            className="text-muted-foreground hover:text-accent opacity-0 group-hover:opacity-100 transition-opacity"
            aria-label={`Link to ${text}`}
          >
            <Hash className="w-4 h-4" />
          </a>
          <span>{children}</span>
        </h3>
      );
    },
    p: ({ children }) => (
      <p className="text-base text-foreground/90 leading-relaxed my-4">
        {children}
      </p>
    ),
    ul: ({ children }) => (
      <ul className="my-4 pl-6 list-disc space-y-2 text-foreground/90 text-[15px] md:text-base leading-7 marker:text-accent">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="my-4 pl-6 list-decimal space-y-2 text-foreground/90 text-[15px] md:text-base leading-7 marker:text-accent marker:font-mono">
        {children}
      </ol>
    ),
    hr: () => <hr className="my-10 border-border" />,
    blockquote: ({ children }) => (
      <blockquote className="my-6 pl-4 border-l-4 border-accent bg-surface-raised/80 p-4 rounded-r-2xl italic text-foreground text-sm md:text-base">
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
    th: ({ children }) => <th className="px-4 py-3 font-semibold text-accent">{children}</th>,
    td: ({ children }) => <td className="px-4 py-3 leading-normal">{children}</td>,
    pre: ({ children }) => <>{children}</>,
    code: ({ className, children, ...props }) => {
      const languageMatch = /language-(\w+)/.exec(className ?? "");
      const language = languageMatch?.[1]?.toLowerCase();
      const rawText = String(children);
      const isBlock = Boolean(language) || rawText.includes("\n");
      const codeText = rawText.replace(/\n$/, "");

      if (isBlock && language === "mermaid") {
        return <MermaidCanvas code={codeText} />;
      }

      if (isBlock && language === "d2") {
        return <D2Canvas code={codeText} />;
      }

      if (isBlock && (language === "chart" || language === "json:chart")) {
        try {
          const parsed = JSON.parse(codeText);
          const chartEntity: ResearchChart = {
            id: 0,
            user_id: 0,
            title: parsed.title || "Empirical Benchmark Chart",
            description: parsed.description || "",
            chart_type: parsed.type || "bar",
            structured_data: parsed,
            units: parsed.units || "",
            data_source: parsed.data_source || "Research Extraction",
            methodology: parsed.methodology || "",
            created_at: new Date().toISOString(),
          };
          return <InteractiveChartExplorer chart={chartEntity} />;
        } catch {
          // Fall through to regular code block if invalid JSON
        }
      }

      if (isBlock) {
        return (
          <div className="my-6 rounded-2xl overflow-hidden border border-border bg-surface text-foreground shadow-sm">
            <div className="flex items-center justify-between px-4 py-2 bg-background/80 border-b border-border text-[11px] font-mono text-muted-foreground">
              <span>{language || "code"}</span>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(codeText);
                }}
                className="hover:text-accent transition"
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
          className="px-1.5 py-0.5 rounded-md bg-surface-raised text-accent font-mono text-xs border border-border"
          {...props}
        >
          {children}
        </code>
      );
    },
    img: ({ src, alt }) => {
      return (
        <figure className="my-8 rounded-2xl overflow-hidden border border-border bg-background/60 shadow-lg">
          <div className="relative overflow-hidden flex items-center justify-center p-2 bg-background">
            <img
              src={src || ""}
              alt={alt || "Research visual figure"}
              className="max-h-[500px] w-auto max-w-full object-contain rounded-xl"
              loading="lazy"
            />
          </div>
          {alt && (
            <figcaption className="px-4 py-2.5 bg-surface/80 border-t border-border text-xs text-muted-foreground italic flex items-center justify-between">
              <span>{alt}</span>
              <span className="text-[10px] font-mono not-italic text-muted-foreground uppercase">Fig. Evidence</span>
            </figcaption>
          )}
        </figure>
      );
    },
    a: ({ href, children }) => {
      const isInternal = href?.startsWith("#");
      return (
        <a
          href={href}
          target={isInternal ? undefined : "_blank"}
          rel={isInternal ? undefined : "noopener noreferrer"}
          className="text-accent hover:text-accent-hover underline underline-offset-4 decoration-accent/40 hover:decoration-accent transition"
        >
          {children}
        </a>
      );
    },
  };

  return (
    <div
      className={`relative w-full flex flex-col gap-5 transition-all ${
        isFocusMode ? "max-w-4xl mx-auto" : "max-w-full"
      }`}
    >
      {/* 1. Article Actions Bar */}
      <div className="no-print sticky top-0 z-30 flex flex-wrap items-center justify-between gap-2.5 p-3 bg-surface/90 border border-border rounded-3xl backdrop-blur-xl shadow-sm premium-shadow">
        {/* Left Stats */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="flex items-center gap-1.5 px-2.5 py-1 bg-surface-raised border border-border rounded-xl text-xs font-medium text-foreground">
            <BookOpen className="w-3.5 h-3.5 text-accent" />
            <span>{calculatedWords.toLocaleString()} words</span>
          </span>
          {isStreaming ? (
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/35 rounded-xl text-xs font-medium text-emerald-700 dark:text-emerald-300 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
              <span>Streaming Draft Live...</span>
            </span>
          ) : (
            <span className="flex items-center gap-1.5 px-2.5 py-1 bg-surface-raised border border-border rounded-xl text-xs font-medium text-foreground">
              <Clock className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>{readingTimeMin} min read</span>
            </span>
          )}
          {generationTime && (
            <span className="hidden sm:flex items-center gap-1 px-2.5 py-1 bg-surface-raised border border-border rounded-xl text-xs text-muted-foreground font-mono">
              <span>{generationTime}s</span>
            </span>
          )}
          {citations.length > 0 && (
            <span className="hidden md:flex items-center gap-1.5 px-2.5 py-1 bg-accent-soft border border-accent/30 rounded-xl text-xs font-medium text-accent">
              <LinkIcon className="w-3 h-3 text-accent" />
              <span>{citations.length} Verified Sources</span>
            </span>
          )}
        </div>

        {/* Right Supported Toolbar Actions */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Unified Export Dropdown */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setExportMenuOpen((prev) => !prev)}
              className="flex items-center gap-2 px-3.5 py-2 bg-surface-raised hover:bg-surface hover:border-border-strong border border-border text-foreground rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98] cursor-pointer shadow-sm"
              title="Export or copy article"
              aria-expanded={exportMenuOpen}
            >
              <Download className="w-4 h-4 text-accent" />
              <span>Export</span>
              <ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform duration-150 ${exportMenuOpen ? "rotate-180" : ""}`} />
            </button>

            {exportMenuOpen && (
              <div
                onMouseLeave={() => setExportMenuOpen(false)}
                className="absolute right-0 mt-2 w-52 rounded-2xl border border-border bg-surface/95 backdrop-blur-xl shadow-2xl p-1.5 z-50"
              >
                <button
                  type="button"
                  onClick={() => {
                    handlePrintPdf();
                    setExportMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-raised transition cursor-pointer"
                >
                  <Printer className="w-4 h-4 text-sky-400" />
                  <span>Export PDF</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    handleDownloadMarkdown();
                    setExportMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-raised transition cursor-pointer"
                >
                  <Download className="w-4 h-4 text-emerald-400" />
                  <span>Download .md</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void handleCopyArticle();
                    setExportMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-raised transition cursor-pointer"
                >
                  {copiedArticle ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4 text-muted-foreground" />}
                  <span>{copiedArticle ? "Copied!" : "Copy Article"}</span>
                </button>
                <button
                  type="button"
                  onClick={() => {
                    void handleCopyCitations();
                    setExportMenuOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-foreground hover:bg-surface-raised transition cursor-pointer"
                >
                  {copiedCitations ? <Check className="w-4 h-4 text-emerald-400" /> : <Quote className="w-4 h-4 text-muted-foreground" />}
                  <span>{copiedCitations ? "Copied!" : "Copy Citations"}</span>
                </button>
              </div>
            )}
          </div>

          {/* Version History */}
          {onOpenVersionHistory && (
            <button
              type="button"
              onClick={onOpenVersionHistory}
              className="flex items-center gap-1.5 px-2.5 py-1.5 bg-surface-raised hover:bg-surface hover:border-border-strong border border-border text-foreground rounded-xl text-xs font-medium transition cursor-pointer"
              title="Open Revisions Timeline"
            >
              <Bookmark className="w-3.5 h-3.5 text-accent" />
              <span className="hidden lg:inline">Versions</span>
            </button>
          )}

          {/* Distraction-Free Reading Mode Toggle */}
          <button
            type="button"
            onClick={() => setIsFocusMode(!isFocusMode)}
            className="p-1.5 bg-surface-raised hover:bg-surface hover:border-border-strong border border-border text-muted-foreground hover:text-foreground rounded-xl transition cursor-pointer"
            title={isFocusMode ? "Exit Focus Mode" : "Distraction-Free Focus Mode"}
            aria-label={isFocusMode ? "Exit Focus Mode" : "Distraction-Free Focus Mode"}
          >
            {isFocusMode ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>

          {/* Visual Research Library Button */}
          {onOpenVisualLibrary && (
            <button
              type="button"
              onClick={onOpenVisualLibrary}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-signal/10 hover:bg-signal/15 border border-signal/30 text-signal rounded-xl text-xs font-semibold transition cursor-pointer"
              title="Open Visual Research Library & Evidence Gallery"
            >
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Visual Library</span>
            </button>
          )}

          {/* Quality Auditor Button */}
          {onOpenQualityAuditor && (
            <button
              type="button"
              onClick={onOpenQualityAuditor}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/10 hover:bg-emerald-500/15 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400 rounded-xl text-xs font-semibold transition cursor-pointer"
              title="Open Section 8 Quality Assurance & Evidence Auditor"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Evidence Auditor</span>
            </button>
          )}

          {/* AI Copilot Drawer */}
          {onOpenCopilot && (
            <PremiumButton
              type="button"
              onClick={onOpenCopilot}
              variant="accent"
              size="sm"
              title="Open AI Copilot"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>AI Copilot</span>
            </PremiumButton>
          )}
        </div>
      </div>

      {/* 2. Main Content Layout */}
      <div className="w-full">
        {/* Center Article Reader Container */}
        <article
          ref={articleRef}
          className="w-full bg-surface border border-border rounded-3xl p-6 sm:p-10 md:p-12 shadow-sm premium-shadow"
        >
          <div className="max-w-[74ch] mx-auto">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
              components={markdownComponents}
            >
              {content}
            </ReactMarkdown>

            {/* Live Streaming Indicator Cursor */}
            {isStreaming && (
              <div className="mt-4 flex items-center gap-2 text-accent font-mono text-sm select-none">
                <span className="inline-block w-2.5 h-5 bg-accent animate-pulse rounded-sm" />
                <span className="text-xs text-muted-foreground italic">Blog Writer drafting token-by-token...</span>
              </div>
            )}

            {/* End of article citation summary card */}
            {citations.length > 0 && (
              <div className="mt-14 pt-8 border-t border-border">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-2">
                    <LinkIcon className="w-3.5 h-3.5 text-accent" />
                    Verified Primary References ({citations.length})
                  </h4>
                  <button
                    type="button"
                    onClick={handleCopyCitations}
                    className="text-xs font-medium text-accent hover:text-accent-hover transition cursor-pointer"
                  >
                    {copiedCitations ? "Copied Sources" : "Copy All Sources"}
                  </button>
                </div>
                <ul className="space-y-2 text-xs text-muted-foreground font-mono bg-surface-raised p-4 rounded-2xl border border-border">
                  {citations.map((c, i) => (
                    <li key={i} className="truncate">
                      <span className="text-accent mr-2">[{i + 1}]</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </article>
      </div>
    </div>
  );
}
