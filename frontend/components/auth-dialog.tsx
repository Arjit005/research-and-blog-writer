"use client";

import React, { useState } from "react";
import { api, User } from "@/lib/api";
import { Mail, Lock, KeyRound, ShieldCheck, AlertCircle, Loader2, Eye, EyeOff } from "lucide-react";

interface AuthDialogProps {
  isOpen: boolean;
  onSuccess: (user: User) => void;
  onClose?: () => void;
}

export function AuthDialog({ isOpen, onSuccess }: AuthDialogProps) {
  const [authMode, setAuthMode] = useState<"password" | "otp">("password");

  // Password flow state
  const [passwordEmail, setPasswordEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [passwordOtp, setPasswordOtp] = useState("");
  const [showOtpField, setShowOtpField] = useState(false);
  const [requestingPasswordOtp, setRequestingPasswordOtp] = useState(false);
  const [passwordOtpSentMsg, setPasswordOtpSentMsg] = useState<string | null>(null);

  // OTP-only flow state
  const [otpStep, setOtpStep] = useState<"email" | "code">("email");
  const [otpEmail, setOtpEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [devCode, setDevCode] = useState<string | null>(null);

  // Shared state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  // Handler for Password login / register (with optional 2FA OTP)
  const handlePasswordAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.loginWithPassword(passwordEmail, password, passwordOtp || undefined);
      if (res.user) {
        onSuccess(res.user);
      } else {
        const user = await api.getMe();
        onSuccess(user);
      }
    } catch (err: any) {
      setError(err.message || "Failed to sign in. Please verify your credentials.");
    } finally {
      setLoading(false);
    }
  };

  // Handler to request OTP for the password tab (2FA)
  const handleRequestPasswordOtp = async () => {
    if (!passwordEmail) {
      setError("Please enter your email address first.");
      return;
    }
    setError(null);
    setRequestingPasswordOtp(true);
    try {
      const res = await api.requestOtp(passwordEmail);
      setShowOtpField(true);
      if (res.dev_code) {
        setPasswordOtp(res.dev_code);
        setPasswordOtpSentMsg(`Code sent! (Dev code: ${res.dev_code})`);
      } else {
        setPasswordOtpSentMsg("Verification code sent to your email!");
      }
    } catch (err: any) {
      setError(err.message || "Failed to send verification passcode.");
    } finally {
      setRequestingPasswordOtp(false);
    }
  };

  // Handler for OTP request
  const handleRequestOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.requestOtp(otpEmail);
      if (res.dev_code) {
        setDevCode(res.dev_code);
        setOtpCode(res.dev_code);
      }
      setOtpStep("code");
    } catch (err: any) {
      setError(err.message || "Failed to send code. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  // Handler for OTP verification
  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.verifyOtp(otpEmail, otpCode);
      if (res.user) {
        onSuccess(res.user);
      } else {
        const user = await api.getMe();
        onSuccess(user);
      }
    } catch (err: any) {
      setError(err.message || "Invalid verification code.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden p-6 text-slate-100">
        <div className="flex items-center gap-3 mb-5">
          <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold">Research Studio</h2>
            <p className="text-sm text-slate-400">Secure Account Authentication</p>
          </div>
        </div>

        {/* Tab switchers */}
        <div className="grid grid-cols-2 gap-1.5 p-1 bg-slate-950/60 rounded-xl border border-slate-800 mb-5 text-sm">
          <button
            type="button"
            onClick={() => {
              setAuthMode("password");
              setError(null);
            }}
            className={`py-1.5 rounded-lg font-medium transition ${
              authMode === "password"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Password + Email
          </button>
          <button
            type="button"
            onClick={() => {
              setAuthMode("otp");
              setError(null);
            }}
            className={`py-1.5 rounded-lg font-medium transition ${
              authMode === "otp"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            Email Passcode (OTP)
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-center gap-2 text-sm text-red-400">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Tab 1: Password with Email + optional OTP */}
        {authMode === "password" ? (
          <form onSubmit={handlePasswordAuth} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Work or Personal Email
              </label>
              <div className="relative">
                <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type="email"
                  required
                  placeholder="name@company.com"
                  value={passwordEmail}
                  onChange={(e) => setPasswordEmail(e.target.value)}
                  className="w-full pl-10 pr-4 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm placeholder:text-slate-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                Password
              </label>
              <div className="relative">
                <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                <input
                  type={showPassword ? "text" : "password"}
                  required
                  placeholder="Enter your password (min 6 chars)"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-10 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm placeholder:text-slate-500"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-3 text-slate-400 hover:text-slate-200"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Optional 2FA OTP Toggle / Field */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <button
                  type="button"
                  onClick={() => setShowOtpField(!showOtpField)}
                  className="text-xs text-indigo-400 hover:underline flex items-center gap-1 font-medium"
                >
                  {showOtpField ? "– Hide 2FA Passcode" : "+ Add Email OTP (2FA Passcode)"}
                </button>
                {showOtpField && (
                  <button
                    type="button"
                    onClick={handleRequestPasswordOtp}
                    disabled={requestingPasswordOtp || !passwordEmail}
                    className="text-xs text-slate-400 hover:text-indigo-300 disabled:opacity-50 flex items-center gap-1"
                  >
                    {requestingPasswordOtp && <Loader2 className="w-3 h-3 animate-spin" />}
                    Send Code to Email
                  </button>
                )}
              </div>

              {showOtpField && (
                <div className="space-y-1.5 animate-in fade-in duration-200">
                  <div className="relative">
                    <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                    <input
                      type="text"
                      maxLength={6}
                      placeholder="6-digit code (if enabled)"
                      value={passwordOtp}
                      onChange={(e) => setPasswordOtp(e.target.value)}
                      className="w-full pl-10 pr-4 py-2 bg-slate-800/80 border border-slate-700 rounded-xl font-mono text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                  {passwordOtpSentMsg && (
                    <p className="text-xs text-emerald-400">{passwordOtpSentMsg}</p>
                  )}
                </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading || !passwordEmail || password.length < 6}
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl font-medium transition flex items-center justify-center gap-2 text-sm"
            >
              {loading && <Loader2 className="w-4 h-4 animate-spin" />}
              Sign In with Password
            </button>
            <p className="text-xs text-center text-slate-500">
              New user? Entering your email and password will register your account automatically.
            </p>
          </form>
        ) : (
          /* Tab 2: Passwordless OTP flow */
          otpStep === "email" ? (
            <form onSubmit={handleRequestOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Work or Personal Email
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                  <input
                    type="email"
                    required
                    placeholder="name@company.com"
                    value={otpEmail}
                    onChange={(e) => setOtpEmail(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 text-sm placeholder:text-slate-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !otpEmail}
                className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl font-medium transition flex items-center justify-center gap-2 text-sm"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Send 6-Digit Passcode
              </button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400">
                    Verification Code
                  </label>
                  <button
                    type="button"
                    onClick={() => setOtpStep("email")}
                    className="text-xs text-indigo-400 hover:underline"
                  >
                    Change Email
                  </button>
                </div>

                <div className="relative">
                  <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                  <input
                    type="text"
                    required
                    maxLength={6}
                    placeholder="123456"
                    value={otpCode}
                    onChange={(e) => setOtpCode(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-slate-800/80 border border-slate-700 rounded-xl tracking-widest text-center text-lg font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <p className="text-xs text-slate-400 mt-1">We sent a 6-digit code to {otpEmail}</p>

                {devCode && (
                  <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-lg text-xs text-amber-300 flex items-center justify-between">
                    <span>Dev Mode Passcode:</span>
                    <span className="font-mono font-bold text-amber-200">{devCode}</span>
                  </div>
                )}
              </div>

              <button
                type="submit"
                disabled={loading || otpCode.length < 6}
                className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-xl font-medium transition flex items-center justify-center gap-2 text-sm"
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                Verify & Enter Studio
              </button>
            </form>
          )
        )}
      </div>
    </div>
  );
}
