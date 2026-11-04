"use client";

import { useState, useEffect } from "react";
import { api, UserKeysInfo } from "@/lib/api";

interface ApiKeysDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onKeysUpdated?: () => void;
}

export function ApiKeysDialog({ isOpen, onClose, onKeysUpdated }: ApiKeysDialogProps) {
  const [keysInfo, setKeysInfo] = useState<UserKeysInfo | null>(null);
  const [geminiKey, setGeminiKey] = useState("");
  const [openrouterKey, setOpenrouterKey] = useState("");
  const [loading, setLoading] = useState(false);
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
      });
      setStatusMsg({ text: "API keys saved successfully!", type: "success" });
      setGeminiKey("");
      setOpenrouterKey("");
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
      <div className="relative w-full max-w-lg rounded-2xl border border-slate-700 bg-slate-900 p-6 shadow-2xl text-slate-100 animate-in fade-in zoom-in-95 duration-150">
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-slate-400 hover:text-white text-xl p-1 leading-none"
          aria-label="Close"
        >
          &times;
        </button>

        <div className="flex items-center gap-3 mb-2">
          <span className="text-2xl">⚙️</span>
          <h2 className="text-xl font-bold tracking-tight">AI Model API Keys</h2>
        </div>
        <p className="text-sm text-slate-400 mb-5">
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
          <div className="p-4 rounded-xl bg-slate-800/80 border border-indigo-500/30">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-semibold text-indigo-300 flex items-center gap-2">
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
            <p className="text-xs text-slate-400 mb-2">
              Free 1,500 requests per day via Google AI Studio with zero credit card required.{" "}
              <a
                href="https://aistudio.google.com/app/apikey"
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:text-indigo-300 underline font-medium"
              >
                Get your free Gemini Key here &rarr;
              </a>
            </p>
            <input
              type="password"
              placeholder={keysInfo?.has_gemini ? "Enter new key to update..." : "AIzaSy..."}
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
              className="w-full px-3.5 py-2 text-sm rounded-lg bg-slate-950 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              autoComplete="off"
            />
          </div>

          {/* OpenRouter Card */}
          <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                <span>🌐 OpenRouter API Key</span>
                <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                  Optional
                </span>
              </label>
              {keysInfo?.has_openrouter && (
                <span className="text-xs text-slate-400 font-mono">
                  {keysInfo.openrouter_masked || "Configured"}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mb-2">
              Used as fallback or custom models.{" "}
              <a
                href="https://openrouter.ai/keys"
                target="_blank"
                rel="noreferrer"
                className="text-indigo-400 hover:text-indigo-300 underline font-medium"
              >
                Get OpenRouter Key &rarr;
              </a>
            </p>
            <input
              type="password"
              placeholder={keysInfo?.has_openrouter ? "Enter new key to update..." : "sk-or-v1-..."}
              value={openrouterKey}
              onChange={(e) => setOpenrouterKey(e.target.value)}
              className="w-full px-3.5 py-2 text-sm rounded-lg bg-slate-950 border border-slate-700 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
              autoComplete="off"
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              className="px-4 py-2 text-sm rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || (!geminiKey && !openrouterKey)}
              className="px-5 py-2 text-sm rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-indigo-600/30"
            >
              {saving ? "Saving..." : "Save Keys"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
