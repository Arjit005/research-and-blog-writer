"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Loader2,
  X,
} from "lucide-react";

interface Claim {
  claim_id: string;
  original_claim: string;
  category: string;
  verification_status: "SUPPORTED" | "PARTIALLY_SUPPORTED" | "CONTRADICTED" | "UNVERIFIABLE" | "OUTDATED" | "CONTEXT_DEPENDENT" | "OPINION_RECOMMENDATION";
  heuristic_confidence: number;
  confidence_evidence: string;
  limitations?: string | null;
}

interface DiagramAudit {
  diagram_id: string;
  syntax_valid: boolean;
  diagram_type: string;
  has_caption: boolean;
  issues: string[];
}

interface AuditReport {
  total_claims_reviewed: number;
  supported_claims: number;
  unverifiable_claims: number;
  contradicted_claims: number;
  citations_valid: boolean | null;
  citations_checked: boolean;
  diagrams_audited: DiagramAudit[];
  publication_status: "PASS" | "REVIEW_REQUIRED" | "BLOCKED";
  blocking_issues: string[];
  claims: Claim[];
  metrics: {
    completeness_score: number;
    citation_provenance_rate: number | null;
  };
}

interface QualityAuditorDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  articleId: number;
}

export function QualityAuditorDrawer({
  isOpen,
  onClose,
  articleId,
}: QualityAuditorDrawerProps) {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !articleId) return;

    let isMounted = true;
    setLoading(true);
    setError(null);

    fetch(`/api/v1/articles/${articleId}/audit`, {
      headers: { Accept: "application/json" },
      credentials: "include",
    })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load audit results.");
        return res.json();
      })
      .then((data: AuditReport) => {
        if (isMounted) setReport(data);
      })
      .catch((err: Error) => {
        if (isMounted) setError(err.message);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, articleId]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-xl bg-surface border-l border-border shadow-2xl flex flex-col font-sans animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-4 border-b border-border flex items-center justify-between bg-surface-raised/40">
        <div className="flex items-center gap-2.5">
          <div className="p-2 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-xl">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
              Claim review
              <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded-md bg-accent/10 text-accent border border-accent/20">
                Section 8
              </span>
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Rule-based review; source support is not verified
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 text-muted-foreground hover:text-foreground rounded-lg hover:bg-surface-raised transition"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {loading && (
          <div className="py-20 flex flex-col items-center justify-center text-muted-foreground gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-accent" />
            <span className="text-xs font-medium">Reviewing article claims and citation links…</span>
          </div>
        )}

        {error && (
          <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-xl text-xs text-red-400">
            {error}
          </div>
        )}

        {report && !loading && (
          <>
            {/* Publication Gate Banner */}
            <div
              className={`p-4 rounded-xl border flex items-center justify-between ${
                report.publication_status === "PASS"
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-300"
                  : report.publication_status === "REVIEW_REQUIRED"
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-300"
                  : "bg-red-500/10 border-red-500/30 text-red-300"
              }`}
            >
              <div className="flex items-center gap-3">
                {report.publication_status === "PASS" ? (
                  <CheckCircle2 className="w-6 h-6 text-emerald-400 shrink-0" />
                ) : report.publication_status === "REVIEW_REQUIRED" ? (
                  <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0" />
                ) : (
                  <XCircle className="w-6 h-6 text-red-400 shrink-0" />
                )}
                <div>
                  <span className="text-xs font-bold uppercase tracking-wider block">
                    Publication Gate: {report.publication_status}
                  </span>
                  <span className="text-[11px] opacity-80 block">
                    Structure score: {Math.round(report.metrics.completeness_score)}/100
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Metrics */}
            <div className="grid grid-cols-3 gap-2.5">
              <div className="p-3 bg-surface-raised border border-border rounded-xl text-center">
                <span className="text-[10px] text-muted-foreground uppercase font-mono block">Claims Reviewed</span>
                <span className="text-base font-bold text-foreground font-mono">{report.total_claims_reviewed}</span>
              </div>
              <div className="p-3 bg-surface-raised border border-border rounded-xl text-center">
                <span className="text-[10px] text-muted-foreground uppercase font-mono block">Source verified</span>
                <span className="text-base font-bold text-emerald-400 font-mono">{report.supported_claims}</span>
              </div>
              <div className="p-3 bg-surface-raised border border-border rounded-xl text-center">
                <span className="text-[10px] text-muted-foreground uppercase font-mono block">Needs evidence</span>
                <span className="text-base font-bold text-amber-400 font-mono">{report.unverifiable_claims}</span>
              </div>
            </div>

            <div className="px-3 py-2.5 bg-surface-raised border border-border rounded-xl text-xs text-muted-foreground">
              Citation provenance: {!report.citations_checked && report.citations_valid !== false
                ? "not checked; no visited-source record is available"
                : report.citations_valid === true
                ? "all citation URLs match recorded visited sources"
                : "missing or unvisited citation URLs were found"}
              <span className="block mt-1">A visited URL does not prove that its content supports a claim.</span>
            </div>

            {/* Blocking Issues */}
            {report.blocking_issues.length > 0 && (
              <div className="space-y-2">
                <span className="text-xs font-bold text-foreground uppercase tracking-wider block">
                  Actionable Findings ({report.blocking_issues.length})
                </span>
                <div className="space-y-1.5">
                  {report.blocking_issues.map((issue, idx) => (
                    <div
                      key={idx}
                      className="p-2.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground flex items-start gap-2"
                    >
                      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <span>{issue}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Structured Evidence Claims */}
            <div className="space-y-2.5">
              <span className="text-xs font-bold text-foreground uppercase tracking-wider block">
                Evidence Claim Inspector
              </span>
              <div className="space-y-2">
                {report.claims.map((claim) => (
                  <div
                    key={claim.claim_id}
                    className="p-3 bg-surface-raised border border-border rounded-xl space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono px-2 py-0.5 bg-surface text-muted-foreground border border-border rounded">
                        {claim.claim_id} • {claim.category}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                          claim.verification_status === "SUPPORTED"
                            ? "bg-emerald-500/10 text-emerald-400"
                            : claim.verification_status === "CONTRADICTED" || claim.verification_status === "OUTDATED"
                            ? "bg-red-500/10 text-red-400"
                            : "bg-amber-500/10 text-amber-400"
                        }`}
                      >
                        {claim.verification_status}
                      </span>
                    </div>
                    <p className="text-xs text-foreground leading-relaxed">&ldquo;{claim.original_claim}&rdquo;</p>
                    <p className="text-[11px] text-muted-foreground">{claim.confidence_evidence}</p>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
