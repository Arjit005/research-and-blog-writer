"use client";

import React, { useState } from "react";
import {
  X,
  User,
  Cpu,
  Sliders,
  Key,
  Bell,
  Shield,
  Palette,
  Check,
  Save,
} from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  userEmail?: string;
  theme: "light" | "dark";
  onThemeChange: (theme: "light" | "dark") => void;
  isSoundMuted: boolean;
  onSoundMuteToggle: () => void;
}

type SettingsTab =
  | "account"
  | "agents"
  | "research"
  | "integrations"
  | "notifications"
  | "security"
  | "appearance";

export function SettingsModal({
  isOpen,
  onClose,
  userEmail,
  theme,
  onThemeChange,
  isSoundMuted,
  onSoundMuteToggle,
}: SettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTab>("account");
  const [savedSuccess, setSavedSuccess] = useState(false);

  // Agent config state
  const [selectedModel, setSelectedModel] = useState("gemini-2.5-flash");
  const [enableFallback, setEnableFallback] = useState(true);
  const [researchDepth, setResearchDepth] = useState("Comprehensive (Default)");
  const [defaultTone, setDefaultTone] = useState("Professional & Authoritative");

  if (!isOpen) return null;

  const handleSave = () => {
    try {
      localStorage.setItem("research-studio:preferred-model", selectedModel);
      localStorage.setItem("research-studio:enable-fallback", String(enableFallback));
      localStorage.setItem("research-studio:research-depth", researchDepth);
      localStorage.setItem("research-studio:default-tone", defaultTone);
      setSavedSuccess(true);
      setTimeout(() => setSavedSuccess(false), 2000);
    } catch {}
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-0 sm:p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div role="dialog" aria-modal="true" aria-labelledby="settings-title" className="w-full h-dvh sm:h-auto sm:max-h-[85vh] max-w-4xl bg-surface border-0 sm:border border-border rounded-none sm:rounded-2xl shadow-2xl overflow-hidden flex flex-col md:flex-row">
        {/* Left Navigation */}
        <div className="w-full md:w-64 bg-surface-raised/50 border-b md:border-b-0 md:border-r border-border p-3 sm:p-4 flex flex-col justify-between shrink-0 max-h-[42dvh] md:max-h-none overflow-y-auto">
          <div className="space-y-1">
            <div className="px-3 py-2 mb-2">
              <h2 id="settings-title" className="text-sm font-bold tracking-tight text-foreground flex items-center gap-2">
                Settings
              </h2>
              <p className="text-[11px] text-muted-foreground">Studio preferences & config</p>
            </div>

            <button
              type="button"
              onClick={() => setActiveTab("account")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "account"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <User className="w-4 h-4" />
              <span>Account & Profile</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("agents")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "agents"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Cpu className="w-4 h-4" />
              <span>Agent Configuration</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("research")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "research"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Sliders className="w-4 h-4" />
              <span>Research Preferences</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("integrations")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "integrations"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Key className="w-4 h-4" />
              <span>API Integrations</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("notifications")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "notifications"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Bell className="w-4 h-4" />
              <span>Notifications</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("security")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "security"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Shield className="w-4 h-4" />
              <span>Security & Sessions</span>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("appearance")}
              className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-medium transition ${
                activeTab === "appearance"
                  ? "bg-accent/10 text-accent border border-accent/20"
                  : "text-muted-foreground hover:text-foreground hover:bg-surface-raised"
              }`}
            >
              <Palette className="w-4 h-4" />
              <span>Appearance & Theme</span>
            </button>
          </div>

          <div className="pt-4 border-t border-border">
            <span className="text-[10px] text-muted-foreground font-mono">v1.2.0 • Enterprise Edition</span>
          </div>
        </div>

        {/* Right Configuration Area */}
        <div className="flex-1 min-h-0 flex flex-col justify-between overflow-y-auto p-4 sm:p-6">
          <div>
            <div className="sticky top-0 z-10 flex items-center justify-between pb-4 mb-5 border-b border-border bg-surface">
              <div>
                <h3 className="text-base font-semibold text-foreground capitalize">
                  {activeTab === "agents" ? "Agent Configuration" : activeTab} Settings
                </h3>
                <p className="text-xs text-muted-foreground">Manage your workspace execution rules</p>
              </div>
              <button
                type="button"
                onClick={onClose}
                className="p-1.5 hover:bg-surface-raised text-muted-foreground hover:text-foreground rounded-lg transition"
                title="Close settings"
                aria-label="Close settings"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Tab: Account */}
            {activeTab === "account" && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">User Email</label>
                  <input
                    type="text"
                    disabled
                    value={userEmail || "Guest User"}
                    className="w-full p-2.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground opacity-80"
                  />
                  <p className="text-[11px] text-muted-foreground mt-1">Managed via session authentication.</p>
                </div>

                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Workspace ID</label>
                  <div className="p-2.5 bg-surface-raised border border-border rounded-xl text-xs font-mono text-muted-foreground">
                    ws-enterprise-prod-01
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Agent Configuration */}
            {activeTab === "agents" && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Primary LLM Provider</label>
                  <select
                    value={selectedModel}
                    onChange={(e) => setSelectedModel(e.target.value)}
                    className="w-full p-2.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground"
                  >
                    <option value="gemini-2.5-flash">Google Gemini 2.5 Flash (Fast & Structured)</option>
                    <option value="gemini-2.5-pro">Google Gemini 2.5 Pro (Deep Research)</option>
                    <option value="groq-llama-3.3-70b">Groq Llama 3.3 70B (High Throughput)</option>
                    <option value="openrouter-free">OpenRouter Multi-Model Free Tier</option>
                  </select>
                </div>

                <div className="p-3 bg-surface-raised border border-border rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-foreground block">Multi-Model Failover Chain</span>
                    <span className="text-[11px] text-muted-foreground">Automatically fallback to secondary models on 429 rate limit.</span>
                  </div>
                  <input
                    type="checkbox"
                    checked={enableFallback}
                    onChange={(e) => setEnableFallback(e.target.checked)}
                    className="w-4 h-4 rounded text-accent focus:ring-accent"
                  />
                </div>
              </div>
            )}

            {/* Tab: Research Preferences */}
            {activeTab === "research" && (
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Research Depth</label>
                  <select
                    value={researchDepth}
                    onChange={(e) => setResearchDepth(e.target.value)}
                    className="w-full p-2.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground"
                  >
                    <option>Comprehensive (Default: 4-agent deep investigation)</option>
                    <option>Fast Executive Brief (2 stages)</option>
                    <option>Academic Deep Dive (Detailed citations & literature)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-foreground mb-1">Default Tone</label>
                  <select
                    value={defaultTone}
                    onChange={(e) => setDefaultTone(e.target.value)}
                    className="w-full p-2.5 bg-surface-raised border border-border rounded-xl text-xs text-foreground"
                  >
                    <option>Professional & Authoritative</option>
                    <option>Technical & Academic</option>
                    <option>Engaging & Accessible</option>
                  </select>
                </div>
              </div>
            )}

            {/* Tab: Integrations */}
            {activeTab === "integrations" && (
              <div className="space-y-3">
                <div className="p-3 bg-surface-raised border border-border rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-foreground block">Google Gemini API</span>
                    <span className="text-[11px] text-muted-foreground">Direct connection via Google AI Studio</span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-md">
                    Configured
                  </span>
                </div>

                <div className="p-3 bg-surface-raised border border-border rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-foreground block">DuckDuckGo Search Engine</span>
                    <span className="text-[11px] text-muted-foreground">Zero-key live web scraping & search</span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-md">
                    Active
                  </span>
                </div>

                <div className="p-3 bg-surface-raised border border-border rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-foreground block">TiDB Cloud Serverless</span>
                    <span className="text-[11px] text-muted-foreground">MySQL-compatible persistent state storage</span>
                  </div>
                  <span className="text-[10px] font-mono px-2 py-0.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-md">
                    Connected
                  </span>
                </div>
              </div>
            )}

            {/* Tab: Notifications */}
            {activeTab === "notifications" && (
              <div className="space-y-3">
                <div className="p-3 bg-surface-raised border border-border rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-xs font-medium text-foreground block">Sound Chime on Completion</span>
                    <span className="text-[11px] text-muted-foreground">Gentle synthesizer tone when article is finalized</span>
                  </div>
                  <button
                    type="button"
                    onClick={onSoundMuteToggle}
                    className={`px-3 py-1 rounded-lg text-xs font-medium border ${
                      !isSoundMuted
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-surface-raised text-muted-foreground border-border"
                    }`}
                  >
                    {!isSoundMuted ? "Enabled" : "Muted"}
                  </button>
                </div>
              </div>
            )}

            {/* Tab: Appearance */}
            {activeTab === "appearance" && (
              <div className="space-y-4">
                <label className="block text-xs font-medium text-foreground mb-2">Interface Theme</label>
                <div className="grid grid-cols-2 gap-3">
                  <button
                    type="button"
                    onClick={() => onThemeChange("dark")}
                    className={`p-3 rounded-xl border text-left transition ${
                      theme === "dark"
                        ? "bg-accent/10 border-accent text-foreground"
                        : "bg-surface-raised border-border text-muted-foreground"
                    }`}
                  >
                    <span className="font-semibold text-xs block mb-1">Linear Dark (Default)</span>
                    <span className="text-[11px] text-muted-foreground block">#080B16 Obsidian & Indigo</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => onThemeChange("light")}
                    className={`p-3 rounded-xl border text-left transition ${
                      theme === "light"
                        ? "bg-accent/10 border-accent text-foreground"
                        : "bg-surface-raised border-border text-muted-foreground"
                    }`}
                  >
                    <span className="font-semibold text-xs block mb-1">Clean Light</span>
                    <span className="text-[11px] text-muted-foreground block">High contrast white & slate</span>
                  </button>
                </div>
              </div>
            )}

            {/* Tab: Security */}
            {activeTab === "security" && (
              <div className="space-y-3">
                <div className="p-3 bg-surface-raised border border-border rounded-xl">
                  <span className="text-xs font-medium text-foreground block">Active Session Security</span>
                  <span className="text-[11px] text-muted-foreground block mt-0.5">
                    Sessions use HttpOnly, SameSite=lax, and __Host- prefixes in production.
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Footer Save & Actions */}
          <div className="pt-4 border-t border-border flex items-center justify-between mt-6">
            <span className="text-xs text-emerald-400 flex items-center gap-1.5">
              {savedSuccess && (
                <>
                  <Check className="w-4 h-4" />
                  <span>Preferences saved successfully!</span>
                </>
              )}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-3.5 py-1.5 bg-surface-raised hover:bg-slate-800 text-muted-foreground hover:text-foreground text-xs rounded-xl transition border border-border"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSave}
                className="px-4 py-1.5 bg-accent hover:bg-accent-strong text-white text-xs font-medium rounded-xl transition shadow-md shadow-accent/20 flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                <span>Save Changes</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
