"use client";

import React, { useEffect, useState } from "react";
import { AmbientWebGLBackdrop } from "@/components/ambient-webgl-bg";
import { PremiumHero } from "@/components/premium-hero";
import { PremiumCard } from "@/components/premium-card";
import { PremiumButton } from "@/components/premium-button";
import {
  Sparkles,
  Search,
  GitBranch,
  PenTool,
  ShieldCheck,
  ArrowRight,
  Cpu,
  Layers,
  Zap,
  Sun,
  Moon,
} from "lucide-react";

interface LandingPageProps {
  onOpenAuth: () => void;
  onEnterGuest: () => void;
}

const AGENTS = [
  {
    step: "01",
    name: "Research Analyst",
    role: "Source Discovery",
    desc: "Crawls live technical docs, papers, and benchmarks to extract verified claims with citations.",
    icon: Search,
    accent: "text-sky-600 dark:text-sky-300",
    glow: "bg-sky-500/10 border-sky-500/25 dark:bg-sky-400/10 dark:border-sky-400/25",
  },
  {
    step: "02",
    name: "Technical Architect",
    role: "Visual Synthesis",
    desc: "Creates clear architecture diagrams and visual charts automatically to explain complex ideas.",
    icon: GitBranch,
    accent: "text-violet-600 dark:text-violet-300",
    glow: "bg-violet-500/10 border-violet-500/25 dark:bg-violet-400/10 dark:border-violet-400/25",
  },
  {
    step: "03",
    name: "Lead Technical Writer",
    role: "Editorial Drafting",
    desc: "Transforms structured research into publication-ready articles with clean formatting, equations, and code examples.",
    icon: PenTool,
    accent: "text-emerald-600 dark:text-emerald-300",
    glow: "bg-emerald-500/10 border-emerald-500/25 dark:bg-emerald-400/10 dark:border-emerald-400/25",
  },
  {
    step: "04",
    name: "Quality Auditor",
    role: "Verification & Copilot",
    desc: "Scores technical accuracy, flags unsupported claims, and powers interactive Copilot revisions.",
    icon: ShieldCheck,
    accent: "text-amber-600 dark:text-amber-300",
    glow: "bg-amber-500/10 border-amber-500/25 dark:bg-amber-400/10 dark:border-amber-400/25",
  },
];

export function LandingPage({ onOpenAuth, onEnterGuest }: LandingPageProps) {
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme");
    if (current === "light" || current === "dark") {
      setTheme(current);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
    if (next === "dark") {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
    try {
      localStorage.setItem("theme", next);
    } catch {
      // ignore storage errors
    }
  };

  return (
    <div className="relative min-h-screen w-full overflow-x-hidden bg-background text-foreground">
      {/* Full-viewport 3D WebGL Spatial Backdrop */}
      <AmbientWebGLBackdrop />

      {/* Sticky Glassmorphic Top Navbar */}
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3.5 sm:px-6">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-500 via-indigo-500 to-emerald-500 text-white shadow-md shadow-sky-500/25 ring-1 ring-white/20">
              <svg
                className="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 2L3 7l9 5 9-5-9-5z" />
                <path d="M3 12l9 5 9-5" />
                <path d="M3 17l9 5 9-5" />
              </svg>
            </div>
            <div>
              <span className="text-sm font-bold tracking-tight text-foreground">
                Research Studio
              </span>
              <span className="ml-2 hidden rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider text-sky-600 dark:border-sky-400/30 dark:bg-sky-400/10 dark:text-sky-300 sm:inline-block">
                AI Studio
              </span>
            </div>
          </div>

          <nav className="hidden items-center gap-6 text-xs font-medium text-muted-foreground md:flex">
            <a href="#engine" className="transition hover:text-foreground">
              3D Engine
            </a>
            <a href="#squad" className="transition hover:text-foreground">
              4-Agent Squad
            </a>
            <a href="#workflow" className="transition hover:text-foreground">
              How It Works
            </a>
          </nav>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              title={theme === "dark" ? "Light mode" : "Dark mode"}
              className="inline-flex h-8 items-center gap-1.5 rounded-xl border border-border/80 bg-surface/70 px-2.5 text-xs font-medium text-muted-foreground transition hover:border-border-strong hover:text-foreground"
            >
              {theme === "dark" ? (
                <>
                  <Sun className="h-3.5 w-3.5 text-amber-400" />
                  <span className="hidden sm:inline">Light</span>
                </>
              ) : (
                <>
                  <Moon className="h-3.5 w-3.5 text-indigo-500" />
                  <span className="hidden sm:inline">Dark</span>
                </>
              )}
            </button>
            <button
              type="button"
              onClick={onEnterGuest}
              className="hidden rounded-xl border border-border/80 bg-surface/70 px-3.5 py-2 text-xs font-medium text-muted-foreground transition hover:border-border-strong hover:text-foreground sm:inline-flex"
            >
              Preview Studio
            </button>
            <PremiumButton onClick={onOpenAuth} variant="accent" size="sm">
              Sign In
              <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
            </PremiumButton>
          </div>
        </div>
      </header>

      {/* Main Marketing Content */}
      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-24 pt-12 sm:px-6 md:pt-16">
        {/* Hero Section */}
        <section
          id="engine"
          className="grid items-center gap-10 lg:grid-cols-12 lg:gap-12"
        >
          <div className="lg:col-span-6">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1 text-[11px] font-mono font-semibold uppercase tracking-[0.18em] text-emerald-700 dark:border-emerald-400/30 dark:bg-emerald-400/10 dark:text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse" />
              Autonomous 4-Agent Research Squad
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl lg:text-[3.25rem] lg:leading-[1.08]">
              Turn any technical question into a{" "}
              <span className="bg-gradient-to-r from-sky-600 via-indigo-600 to-emerald-600 dark:from-sky-300 dark:via-indigo-300 dark:to-emerald-300 bg-clip-text text-transparent">
                publication-ready
              </span>{" "}
              brief.
            </h1>

            <p className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
              Research Studio coordinates four specialized AI assistants—from live
              source discovery and visual diagrams to quality checking and
              interactive editing.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3.5">
              <PremiumButton onClick={onOpenAuth} variant="accent" size="lg">
                Sign In to Launch Studio
                <ArrowRight className="ml-2 h-4 w-4" />
              </PremiumButton>
              <button
                type="button"
                onClick={onEnterGuest}
                className="inline-flex h-11 items-center gap-2 rounded-xl border border-border bg-surface/80 px-5 text-sm font-medium text-foreground backdrop-blur-md transition hover:border-border-strong hover:bg-surface-raised"
              >
                Explore Workspace
              </button>
            </div>

            <div className="mt-8 grid grid-cols-3 gap-4 border-t border-border/60 pt-6">
              <div>
                <div className="text-xl font-bold text-foreground">4 Specialists</div>
                <div className="text-xs text-muted-foreground">Working Together</div>
              </div>
              <div>
                <div className="text-xl font-bold text-sky-600 dark:text-sky-300">Visual Charts</div>
                <div className="text-xs text-muted-foreground">Auto-Generated</div>
              </div>
              <div>
                <div className="text-xl font-bold text-emerald-600 dark:text-emerald-300">Live Progress</div>
                <div className="text-xs text-muted-foreground">Real-Time Updates</div>
              </div>
            </div>
          </div>

          {/* Right: Interactive 3D Research-to-Story Engine */}
          <div className="lg:col-span-6">
            <PremiumCard
              tilt
              hover={false}
              bordered
              className="bg-surface/80 backdrop-blur-xl shadow-2xl shadow-sky-500/10"
            >
              <PremiumHero />
            </PremiumCard>
          </div>
        </section>

        {/* 4-Agent Squad Section */}
        <section id="squad" className="mt-24">
          <div className="mb-10 max-w-2xl">
            <div className="mb-2 text-xs font-mono font-semibold uppercase tracking-[0.2em] text-sky-300">
              The Architecture
            </div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              Four specialized agents. One cohesive desk.
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground sm:text-base">
              Every article passes through a structured multi-agent pipeline so
              claims are verified, diagrams are accurate, and prose is crisp.
            </p>
          </div>

          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {AGENTS.map((agent) => {
              const Icon = agent.icon;
              return (
                <PremiumCard
                  key={agent.step}
                  tilt
                  bordered
                  className="bg-surface/75 backdrop-blur-md"
                >
                  <div className="flex items-center justify-between">
                    <div
                      className={`flex h-10 w-10 items-center justify-center rounded-xl border ${agent.glow}`}
                    >
                      <Icon className={`h-5 w-5 ${agent.accent}`} />
                    </div>
                    <span className="font-mono text-xs text-muted-foreground">
                      {agent.step}
                    </span>
                  </div>
                  <h3 className="mt-5 text-lg font-semibold text-foreground">
                    {agent.name}
                  </h3>
                  <div className={`text-xs font-medium ${agent.accent}`}>
                    {agent.role}
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                    {agent.desc}
                  </p>
                </PremiumCard>
              );
            })}
          </div>
        </section>

        {/* Workflow Section */}
        <section id="workflow" className="mt-24">
          <PremiumCard
            bordered
            hover={false}
            className="bg-gradient-to-br from-surface/90 via-surface/80 to-surface-raised/80 backdrop-blur-xl p-8 sm:p-10"
          >
            <div className="grid gap-8 md:grid-cols-3">
              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-400/30 bg-sky-400/10 text-sky-300">
                  <Cpu className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    1. Commission a Topic
                  </h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Enter any engineering domain, choose tone & depth, and launch
                    the squad.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-violet-400/30 bg-violet-400/10 text-violet-300">
                  <Layers className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    2. Watch Live Synthesis
                  </h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Watch research progress, verified sources, and visual
                    diagrams come together live.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-emerald-400/30 bg-emerald-400/10 text-emerald-300">
                  <Zap className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    3. Audit & Publish
                  </h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">
                    Run the Quality Auditor, refine with Editorial Copilot, and
                    export Markdown.
                  </p>
                </div>
              </div>
            </div>
          </PremiumCard>
        </section>

        {/* Bottom CTA */}
        <section className="mt-20 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            Ready to enter your Research Studio?
          </h2>
          <p className="mx-auto mt-2.5 max-w-md text-sm text-muted-foreground">
            Sign in to save articles, manage API keys, and collaborate with your
            autonomous research squad.
          </p>
          <div className="mt-6 flex justify-center gap-3">
            <PremiumButton onClick={onOpenAuth} variant="accent" size="lg">
              Sign In Now
              <ArrowRight className="ml-2 h-4 w-4" />
            </PremiumButton>
          </div>
        </section>
      </main>
    </div>
  );
}
