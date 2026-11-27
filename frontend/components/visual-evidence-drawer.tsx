"use client";

import React, { useEffect, useState } from "react";
import {
  ShieldCheck,
  CheckCircle2,
  ExternalLink,
  Link as LinkIcon,
  X,
  FileCode,
  Sparkles,
} from "lucide-react";
import { api, ResearchVisual, EvidenceLink } from "@/lib/api";

interface VisualEvidenceDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  visual: ResearchVisual | null;
}

export function VisualEvidenceDrawer({
  isOpen,
  onClose,
  visual,
}: VisualEvidenceDrawerProps) {
  const [links, setLinks] = useState<EvidenceLink[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen || !visual) return;
    const fetchEvidence = async () => {
      setLoading(true);
      try {
        const res = await api.getEvidenceLinks({ visual_id: visual.id });
        setLinks(res);
      } catch (err) {
        console.error("Failed to load visual evidence links:", err);
      } finally {
        setLoading(false);
      }
    };
    void fetchEvidence();
  }, [isOpen, visual]);

  if (!isOpen || !visual) return null;

  const isAI = visual.origin_type === "ai_generated";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Visual Evidence and Traceability Inspector"
      className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col text-slate-100 animate-in slide-in-from-right duration-200"
    >
      {/* 1. Header */}
      <div className="flex items-center justify-between p-4 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-lg">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
              Visual Evidence Trace
            </h3>
            <span className="text-[10px] text-slate-400 font-mono">
              Provenance & Claim Grounding
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* 2. Visual Summary */}
      <div className="p-4 border-b border-slate-800/80 bg-slate-950/40">
        <div className="flex items-center gap-3">
          <div className="w-16 h-16 rounded-xl bg-slate-950 border border-slate-800 overflow-hidden flex items-center justify-center shrink-0">
            {visual.thumbnail_url || visual.source_url ? (
              <img
                src={visual.thumbnail_url || visual.source_url || ""}
                alt={visual.title}
                className="w-full h-full object-cover"
              />
            ) : (
              <FileCode className="w-6 h-6 text-indigo-400" />
            )}
          </div>
          <div className="min-w-0">
            <h4 className="text-xs font-bold text-slate-100 line-clamp-1">{visual.title}</h4>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                {visual.visual_type.toUpperCase()}
              </span>
              {isAI && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                  <Sparkles className="w-3 h-3" />
                  AI Gen
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 3. Provenance & Attributions */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-mono block mb-2">
            Provenance Metadata
          </span>
          <div className="p-3.5 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2 text-xs font-mono">
            <div className="flex justify-between items-center text-slate-400">
              <span className="text-slate-500">Origin Class:</span>
              <span className="text-slate-200 capitalize">{visual.origin_type.replace(/_/g, " ")}</span>
            </div>
            {visual.source_title && (
              <div className="flex justify-between items-center text-slate-400">
                <span className="text-slate-500">Source Document:</span>
                <span className="text-indigo-300 truncate max-w-[180px]">{visual.source_title}</span>
              </div>
            )}
            {visual.license_information && (
              <div className="flex justify-between items-center text-slate-400">
                <span className="text-slate-500">License:</span>
                <span className="text-slate-300">{visual.license_information}</span>
              </div>
            )}
            <div className="flex justify-between items-center text-slate-400">
              <span className="text-slate-500">Retrieved:</span>
              <span className="text-slate-300">{visual.retrieval_timestamp.split("T")[0]}</span>
            </div>
          </div>
        </div>

        {/* Supporting Evidence Connections */}
        <div>
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider font-mono block mb-2">
            Connected Factual Claims & Citations
          </span>

          {loading ? (
            <div className="p-8 text-center text-xs text-slate-500 font-mono animate-pulse">
              Tracing evidence graph…
            </div>
          ) : links.length > 0 ? (
            <div className="space-y-2.5">
              {links.map((link) => (
                <div
                  key={link.id}
                  className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl text-xs space-y-1.5"
                >
                  <div className="flex items-center justify-between font-mono text-[10px]">
                    <span className="text-emerald-400 flex items-center gap-1 font-bold">
                      {link.evidence_status === "reviewed" ? (
                        <CheckCircle2 className="w-3 h-3" />
                      ) : (
                        <ShieldCheck className="w-3 h-3" />
                      )}
                      {link.evidence_status.toUpperCase()}
                    </span>
                    {link.claim_id && (
                      <span className="text-slate-500">Claim ID: {link.claim_id}</span>
                    )}
                  </div>
                  {link.report_section && (
                    <p className="text-slate-300 font-medium">
                      Grounds Section: <strong className="text-indigo-300">{link.report_section}</strong>
                    </p>
                  )}
                  {link.citation_url && (
                    <a
                      href={link.citation_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300 underline truncate pt-1"
                    >
                      <LinkIcon className="w-3 h-3 shrink-0" />
                      <span>{link.citation_url}</span>
                    </a>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="p-4 bg-slate-950/40 border border-slate-800/80 rounded-xl text-xs text-slate-400">
              <p className="leading-relaxed">
                No claim-to-source links are attached to this visual yet. Check the original source before
                treating it as evidence or reusing it.
              </p>
            </div>
          )}
        </div>

        {/* Source link */}
        {visual.source_url && (
          <div className="pt-2">
            <a
              href={visual.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition shadow-md shadow-indigo-600/20"
            >
              <ExternalLink className="w-4 h-4" />
              <span>Verify at Original Source</span>
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
