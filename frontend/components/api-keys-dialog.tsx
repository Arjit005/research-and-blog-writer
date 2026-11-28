"use client";

import { useState, useEffect } from "react";
import { api, UserKeysInfo } from "@/lib/api";
import { useDialogAccessibility } from "@/hooks/use-dialog-accessibility";

interface ApiKeysDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onKeysUpdated?: () => void;
}

export function ApiKeysDialog({ isOpen, onClose, onKeysUpdated }: ApiKeysDialogProps) {
  const dialogRef = useDialogAccessibility<HTMLDivElement>(isOpen, onClose);
  const [keysInfo, setKeysInfo] = useState<UserKeysInfo | null>(null);
  const [geminiKey, setGeminiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [beatapiKey, setBeatapiKey] = useState("");
  const [_loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMsg, setStatusMsg] = useState<{ text: string; type: "success" | "error" } | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadKeys();
    }
  }, [isOpen]);

  async function loadKeys() {
    setLoading(true);
    setStatusMsg(null);
    try {
      const info = await api.getUserKeys();
      setKeysInfo(info);
    } catch {
      // User might be unauthenticated or error
      setKeysInfo(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setStatusMsg(null);
    try {
      await api.saveUserKeys({
        gemini_api_key: geminiKey.trim() || undefined,
        openrouter_api_key: openrouterKey.trim() || undefined,
        beatapi_key: beatapiKey.trim() || undefined,
      });
      setStatusMsg({ text: "API keys saved successfully!", type: "success" });
      setGeminiKey("");
      setOpenrouterKey("");
      setBeatapiKey("");
      await loadKeys();
      onKeysUpdated?.();
      setTimeout(() => {
        onClose();
      }, 1200);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to save API keys";
      setStatusMsg({ text: msg, type: "error" });
    } finally {
      setSaving(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="api-keys-title" className="relative w-full max-w-lg rounded-2xl border border-border bg-surface p-6 shadow-2xl text-foreground animate-in fade-in zoom-in-95 duration-150">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-muted-foreground hover:text-white text-xl p-1 leading-none"
          aria-label="Close"
        >
          &times;
        </button>

        <div className="flex items-center gap-3 mb-2">
          <span className="text-2xl">⚙️</span>
          <h2 id="api-keys-title" className="text-xl font-bold tracking-tight">AI Model API Keys</h2>
        </div>
        <p className="text-sm text-muted-foreground mb-5">
          Configure your personal AI provider keys to bypass OpenRouter rate limits (50 req/day).
        </p>

        {statusMsg && (
          <div
            className={`mb-4 rounded-lg p-3 text-sm font-medium ${
              statusMsg.type === "success"
                ? "bg-emerald-950/80 border border-emerald-500/40 text-emerald-300"
                : "bg-rose-950/80 border border-rose-500/40 text-rose-300"
            }`}
          >
            {statusMsg.text}
          </div>
        )}

        <form onSubmit={handleSave} className="space-y-5">
          {/* Google Gemini Card */}
          <div className="p-4 rounded-xl bg-surface-raised/80 border border-signal/30">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-semibold text-signal flex items-center gap-2">
                <span>✨ Google Gemini API Key</span>
                <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  Recommended: 1,500 free req/day
                </span>
              </label>
              {keysInfo?.has_gemini && (
                <span className="text-xs text-emerald-400 font-mono">
                  {keysInfo.gemini_masked || "Configured"}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mb-2">
              Free 1,500 requests per day via Google AI Studio with zero credit card required.{" "}
              <a
                href="https://aistudio.google.com/app/apikey"
                target="_blank"
                rel="noreferrer"
                className="text-signal hover:text-signal underline font-medium"
              >
                Get your free Gemini Key here &rarr;
              </a>
            </p>
            <input
              type="password"
              placeholder={keysInfo?.has_gemini ? "Enter new key to update..." : "AIzaSy..."}
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
              className="w-full px-3.5 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder-slate-500 focus:outline-none focus:border-signal"
              autoComplete="off"
            />
          </div>

          {/* OpenRouter Card */}
          <div className="p-4 rounded-xl bg-surface-raised/50 border border-border">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-semibold text-foreground flex items-center gap-2">
                <span>🌐 OpenRouter API Key</span>
                <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-surface-raised text-foreground">
                  Optional
                </span>
              </label>
              {keysInfo?.has_openrouter && (
                <span className="text-xs text-muted-foreground font-mono">
                  {keysInfo.openrouter_masked || "Configured"}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mb-2">
              Used as fallback or custom models.{" "}
              <a
                href="https://openrouter.ai/keys"
                target="_blank"
                rel="noreferrer"
                className="text-signal hover:text-signal underline font-medium"
              >
                Get OpenRouter Key &rarr;
              </a>
            </p>
            <input
              type="password"
              placeholder={keysInfo?.has_openrouter ? "Enter new key to update..." : "sk-or-v1-..."}
              value={openrouterKey}
              onChange={(e) => setOpenrouterKey(e.target.value)}
              className="w-full px-3.5 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder-slate-500 focus:outline-none focus:border-signal"
              autoComplete="off"
            />
          </div>

          {/* BeatAPI Card */}
          <div className="p-4 rounded-xl bg-surface-raised/50 border border-border">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-semibold text-foreground flex items-center gap-2">
                <span>⚡ BeatAPI Key</span>
                <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-surface-raised text-foreground">
                  Free models: GLM 5.3, DeepSeek V4.1, Hunyuan
                </span>
              </label>
              {keysInfo?.has_beatapi && (
                <span className="text-xs text-muted-foreground font-mono">
                  {keysInfo.beatapi_masked || "Configured"}
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground mb-2">
              Free fallback models from BeatAPI.{" "}
              <a
                href="https://beatapi.io"
                target="_blank"
                rel="noreferrer"
                className="text-signal hover:text-signal underline font-medium"
              >
                Get BeatAPI Key &rarr;
              </a>
            </p>
            <input
              type="password"
              placeholder={keysInfo?.has_beatapi ? "Enter new key to update..." : "beat-..."}
              value={beatapiKey}
              onChange={(e) => setBeatapiKey(e.target.value)}
              className="w-full px-3.5 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder-slate-500 focus:outline-none focus:border-signal"
              autoComplete="off"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-surface-raised hover:bg-surface-raised text-foreground font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || (!geminiKey && !openrouterKey && !beatapiKey)}
              className="px-5 py-2 text-sm rounded-lg bg-accent hover:bg-accent-hover text-accent-foreground font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-accent/20"
            >
              {saving ? "Saving..." : "Save Keys"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
