"use client";

import React, { useEffect, useRef, useState } from "react";
import { api, errorMessage, User } from "@/lib/api";
import {
  Mail,
  Lock,
  KeyRound,
  AlertCircle,
  Loader2,
  Eye,
  EyeOff,
  X,
  Sparkles,
  ArrowRight,
  ShieldCheck,
  ChevronRight,
  Check,
} from "lucide-react";
import { signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "@/lib/firebase";

interface AuthDialogProps {
  isOpen: boolean;
  onSuccess: (user: User) => void;
  onClose?: () => void;
}

export function AuthDialog({ isOpen, onSuccess, onClose }: AuthDialogProps) {
  const [authMode, setAuthMode] = useState<"password" | "otp">("password");
  const dialogRef = useRef<HTMLDivElement>(null);

  // Password flow state
  const [passwordEmail, setPasswordEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
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

  // Focus trap and accessibility
  useEffect(() => {
    if (!isOpen) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusableSelector =
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

    const focusFirstField = window.setTimeout(() => {
      const first = dialog.querySelector<HTMLElement>(focusableSelector);
      first?.focus();
    }, 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        return;
      }
      if (event.key !== "Tab") return;

      const focusables = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector)).filter(
        (element) => element.offsetParent !== null
      );
      if (focusables.length === 0) return;

      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(focusFirstField);
      document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Handler for Google Sign-In via Firebase popup
  const handleGoogleSignIn = async () => {
    setError(null);
    setLoading(true);
    try {
      const userCredential = await signInWithPopup(auth, googleProvider);
      const idToken = await userCredential.user.getIdToken();
      const res = await api.loginWithGoogle(idToken);
      if (res.user) {
        onSuccess(res.user);
      } else {
        const user = await api.getMe();
        onSuccess(user);
      }
    } catch (err: unknown) {
      const firebaseErr = err as { code?: string; message?: string };
      if (
        firebaseErr?.code === "auth/popup-closed-by-user" ||
        firebaseErr?.code === "auth/cancelled-popup-request"
      ) {
        return;
      }
      setError(errorMessage(err, "Google sign-in failed. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  // Handler for password login
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
    } catch (err) {
      setError(errorMessage(err, "Failed to sign in. Please verify your credentials."));
    } finally {
      setLoading(false);
    }
  };

  // Handler to request OTP for 2FA
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
    } catch (err) {
      setError(errorMessage(err, "Failed to send verification passcode."));
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
    } catch (err) {
      setError(errorMessage(err, "Failed to send code. Please try again."));
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
    } catch (err) {
      setError(errorMessage(err, "Invalid verification code."));
    } finally {
      setLoading(false);
    }
  };

  // Switch to new account creation / OTP flow
  const handleCreateAccountClick = () => {
    setError(null);
    if (passwordEmail && !otpEmail) {
      setOtpEmail(passwordEmail);
    }
    setOtpStep("email");
    setAuthMode("otp");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-3 sm:p-6 md:p-8 animate-in fade-in duration-200 overflow-y-auto"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
        className="relative w-full max-w-4xl bg-white rounded-3xl shadow-2xl overflow-hidden flex flex-col md:flex-row my-auto border border-slate-200/80"
      >
        {/* Close Button */}
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sign-in dialog"
            className="absolute right-4 top-4 z-20 p-2 rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-400"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        )}

        {/* =========================================================================
            LEFT 40% PANEL: Dark Navy, Branding, Welcome Back, Abstract Wave Graphics
           ========================================================================= */}
        <div className="relative md:w-5/12 bg-gradient-to-br from-[#0a0f1d] via-[#0f172a] to-[#1e1b4b] text-white p-8 md:p-10 flex flex-col justify-between overflow-hidden shrink-0 min-h-[260px] md:min-h-[580px]">
          {/* Subtle Ambient Radial Lighting */}
          <div className="absolute -top-20 -left-20 w-72 h-72 bg-indigo-500/20 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-20 -right-20 w-80 h-80 bg-violet-600/25 rounded-full blur-3xl pointer-events-none" />

          {/* Top Brand Header */}
          <div className="relative z-10">
            <div className="inline-flex items-center gap-2.5 px-3 py-1.5 rounded-full bg-white/10 backdrop-blur-md border border-white/15 text-indigo-200 text-xs font-medium tracking-wide">
              <div className="w-5 h-5 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center shadow-sm">
                <Sparkles className="w-3 h-3 text-white" aria-hidden="true" />
              </div>
              <span className="font-semibold text-white tracking-tight">Research Studio</span>
            </div>

            <div className="mt-8 md:mt-12">
              <h2 className="text-3xl md:text-4xl font-extrabold tracking-tight text-white leading-tight">
                Welcome <br className="hidden md:inline" />
                Back!
              </h2>
              <p className="mt-3 text-sm text-slate-300/90 leading-relaxed max-w-xs">
                Empowering AI research squads, multi-source synthesis, and automated publications in one studio.
              </p>
            </div>
          </div>

          {/* Abstract Wave Pattern (Geometric Curves) */}
          <div className="relative z-0 mt-6 md:mt-auto pt-4 pointer-events-none select-none">
            <svg
              className="w-full h-36 md:h-48 text-indigo-400/20 overflow-visible"
              viewBox="0 0 400 200"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
            >
              <defs>
                <linearGradient id="waveGradA" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity="0.45" />
                  <stop offset="50%" stopColor="#a855f7" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="#6366f1" stopOpacity="0.05" />
                </linearGradient>
                <linearGradient id="waveGradB" x1="0%" y1="100%" x2="100%" y2="0%">
                  <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.2" />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity="0.5" />
                </linearGradient>
              </defs>
              <path
                d="M -20 160 C 80 80, 160 220, 260 120 C 340 40, 390 100, 440 60"
                stroke="url(#waveGradA)"
                strokeWidth="2.5"
                fill="none"
              />
              <path
                d="M -20 180 C 70 110, 150 240, 250 140 C 330 60, 390 130, 440 90"
                stroke="url(#waveGradA)"
                strokeWidth="2"
                strokeDasharray="4 6"
                fill="none"
              />
              <path
                d="M -20 130 C 90 60, 170 180, 280 90 C 350 20, 400 80, 450 40"
                stroke="url(#waveGradB)"
                strokeWidth="1.5"
                fill="none"
              />
              <circle cx="260" cy="120" r="4" fill="#a855f7" />
              <circle cx="160" cy="220" r="3" fill="#818cf8" />
              <circle cx="90" cy="60" r="3.5" fill="#38bdf8" />
            </svg>
          </div>

          {/* Left Footer Badges */}
          <div className="relative z-10 pt-4 border-t border-white/10 flex items-center justify-between text-[11px] text-slate-400">
            <span>v2.4 Technical Studio</span>
            <span className="flex items-center gap-1 text-emerald-400 font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
              Protected & Verified
            </span>
          </div>
        </div>

        {/* =========================================================================
            RIGHT 60% PANEL: Clean White, Centered Login Form, SaaS Hierarchy
           ========================================================================= */}
        <div className="md:w-7/12 p-8 md:p-12 flex flex-col justify-center bg-white text-slate-900">
          <div className="max-w-md w-full mx-auto">
            {/* Header / Subtitle */}
            <div className="mb-6">
              <h3 id="auth-dialog-title" className="text-2xl font-bold tracking-tight text-slate-900">
                {authMode === "password" ? "Sign in to account" : "Email Passcode Sign-In"}
              </h3>
              <p className="text-sm text-slate-500 mt-1">
                {authMode === "password"
                  ? "Enter your credentials to access your research workspace"
                  : "We'll send a single-use verification code to your inbox"}
              </p>
            </div>

            {/* Prominent White Outlined Google Sign-In Button */}
            <button
              type="button"
              onClick={handleGoogleSignIn}
              disabled={loading}
              className="w-full py-2.5 px-4 bg-white hover:bg-slate-50 active:bg-slate-100 text-slate-700 font-medium border border-slate-300 rounded-xl transition duration-150 flex items-center justify-center gap-3 text-sm shadow-sm hover:shadow focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-50 disabled:cursor-not-allowed group"
            >
              {loading ? (
                <Loader2 className="w-4 h-4 animate-spin text-slate-500" />
              ) : (
                <svg className="w-4 h-4 shrink-0 transition-transform group-hover:scale-105" viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
              )}
              <span>Continue with Google</span>
            </button>

            {/* Clean Modern Divider */}
            <div className="relative flex items-center justify-center my-5">
              <div className="border-t border-slate-200 w-full" />
              <span className="bg-white px-3 text-xs uppercase tracking-wider text-slate-400 font-semibold absolute">
                or with email
              </span>
            </div>

            {/* Error Banner */}
            {error && (
              <div
                role="alert"
                className="mb-4 p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5 text-xs text-red-600 animate-in fade-in"
              >
                <AlertCircle className="w-4 h-4 shrink-0 text-red-500 mt-0.5" aria-hidden="true" />
                <span className="leading-relaxed">{error}</span>
              </div>
            )}

            {/* Primary Flow: Email & Password Form */}
            {authMode === "password" ? (
              <form onSubmit={handlePasswordAuth} className="space-y-4">
                <div>
                  <label htmlFor="auth-email-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" aria-hidden="true" />
                    <input
                      id="auth-email-input"
                      type="email"
                      required
                      autoComplete="email"
                      placeholder="name@company.com"
                      value={passwordEmail}
                      onChange={(e) => setPasswordEmail(e.target.value)}
                      className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 text-sm placeholder:text-slate-400 text-slate-900 transition"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label htmlFor="auth-password-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                      Password
                    </label>
                    <button
                      type="button"
                      onClick={() => {
                        if (passwordEmail && !otpEmail) {
                          setOtpEmail(passwordEmail);
                        }
                        setAuthMode("otp");
                        setOtpStep("email");
                        setError(null);
                      }}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900 hover:underline transition"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" aria-hidden="true" />
                    <input
                      id="auth-password-input"
                      type={showPassword ? "text" : "password"}
                      required
                      autoComplete="current-password"
                      placeholder="••••••••"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="w-full pl-10 pr-10 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 text-sm placeholder:text-slate-400 text-slate-900 transition"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      className="absolute right-3 top-2.5 p-1 rounded-md text-slate-400 hover:text-slate-700 transition"
                    >
                      {showPassword ? (
                        <EyeOff className="w-4 h-4" aria-hidden="true" />
                      ) : (
                        <Eye className="w-4 h-4" aria-hidden="true" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Remember Me and Optional 2FA row */}
                <div className="flex items-center justify-between pt-0.5">
                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <div
                      role="checkbox"
                      aria-checked={rememberMe}
                      tabIndex={0}
                      onClick={() => setRememberMe(!rememberMe)}
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          setRememberMe(!rememberMe);
                        }
                      }}
                      className={`w-4 h-4 rounded border flex items-center justify-center transition ${
                        rememberMe
                          ? "bg-slate-900 border-slate-900 text-white"
                          : "border-slate-300 bg-white"
                      }`}
                    >
                      {rememberMe && <Check className="w-3 h-3 stroke-[3]" aria-hidden="true" />}
                    </div>
                    <span className="text-xs text-slate-600 font-medium">Remember me</span>
                  </label>

                  <button
                    type="button"
                    onClick={() => setShowOtpField(!showOtpField)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium transition"
                  >
                    {showOtpField ? "– Hide 2FA" : "+ 2FA Code"}
                  </button>
                </div>

                {/* Optional 2FA Input Container */}
                {showOtpField && (
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-2 animate-in fade-in duration-200">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-slate-600 font-medium">Email 2FA Passcode</span>
                      <button
                        type="button"
                        onClick={handleRequestPasswordOtp}
                        disabled={requestingPasswordOtp || !passwordEmail}
                        className="text-indigo-600 hover:underline font-medium disabled:opacity-50 flex items-center gap-1"
                      >
                        {requestingPasswordOtp && <Loader2 className="w-3 h-3 animate-spin" />}
                        Send code
                      </button>
                    </div>
                    <div className="relative">
                      <KeyRound className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                      <input
                        type="text"
                        maxLength={6}
                        placeholder="6-digit code"
                        value={passwordOtp}
                        onChange={(e) => setPasswordOtp(e.target.value)}
                        className="w-full pl-9 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg font-mono text-sm tracking-wider focus:outline-none focus:ring-2 focus:ring-slate-900"
                      />
                    </div>
                    {passwordOtpSentMsg && (
                      <p className="text-[11px] text-emerald-600 font-medium">{passwordOtpSentMsg}</p>
                    )}
                  </div>
                )}

                {/* Solid Black Rounded Primary Login Button */}
                <button
                  type="submit"
                  disabled={loading || !passwordEmail || password.length < 6}
                  className="w-full mt-2 py-3 px-4 bg-slate-950 hover:bg-black active:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-full font-semibold transition-all duration-150 flex items-center justify-center gap-2 text-sm shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <span>Login</span>
                  )}
                </button>

                {/* Secondary Passcode Switcher */}
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => {
                      if (passwordEmail && !otpEmail) {
                        setOtpEmail(passwordEmail);
                      }
                      setAuthMode("otp");
                      setOtpStep("email");
                      setError(null);
                    }}
                    className="w-full py-2 px-3 rounded-xl border border-slate-200 hover:border-slate-300 bg-slate-50 hover:bg-slate-100 text-xs text-slate-600 hover:text-slate-900 transition flex items-center justify-between group"
                  >
                    <span className="flex items-center gap-2 font-medium">
                      <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" aria-hidden="true" />
                      Sign in with email passcode instead (passwordless)
                    </span>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-700 transition-transform group-hover:translate-x-0.5" />
                  </button>
                </div>
              </form>
            ) : (
              /* Secondary Passwordless OTP Flow */
              <div className="space-y-4">
                <div className="flex items-center justify-between pb-1 border-b border-slate-100">
                  <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5" aria-hidden="true" />
                    Email Passcode Flow
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setAuthMode("password");
                      setError(null);
                    }}
                    className="text-xs font-medium text-slate-500 hover:text-slate-900 transition"
                  >
                    Back to Password
                  </button>
                </div>

                {otpStep === "email" ? (
                  <form onSubmit={handleRequestOtp} className="space-y-4">
                    <div>
                      <label htmlFor="otp-email-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1.5">
                        Email address
                      </label>
                      <div className="relative">
                        <Mail className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" aria-hidden="true" />
                        <input
                          id="otp-email-input"
                          type="email"
                          required
                          autoComplete="email"
                          placeholder="name@company.com"
                          value={otpEmail}
                          onChange={(e) => setOtpEmail(e.target.value)}
                          className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 focus:border-slate-900 text-sm placeholder:text-slate-400 text-slate-900 transition"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={loading || !otpEmail}
                      className="w-full py-3 px-4 bg-slate-950 hover:bg-black active:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-full font-semibold transition-all duration-150 flex items-center justify-center gap-2 text-sm shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
                    >
                      {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <>
                          <span>Send Passcode</span>
                          <ArrowRight className="w-4 h-4" aria-hidden="true" />
                        </>
                      )}
                    </button>
                  </form>
                ) : (
                  <form onSubmit={handleVerifyOtp} className="space-y-4">
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label htmlFor="otp-code-input" className="block text-xs font-semibold uppercase tracking-wider text-slate-700">
                          Verification Code
                        </label>
                        <button
                          type="button"
                          onClick={() => setOtpStep("email")}
                          className="text-xs font-medium text-indigo-600 hover:underline"
                        >
                          Change Email
                        </button>
                      </div>

                      <div className="relative">
                        <KeyRound className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" aria-hidden="true" />
                        <input
                          id="otp-code-input"
                          type="text"
                          required
                          maxLength={6}
                          placeholder="123456"
                          value={otpCode}
                          onChange={(e) => setOtpCode(e.target.value)}
                          className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-200 rounded-xl tracking-widest text-center text-lg font-mono focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-900 text-slate-900 transition"
                        />
                      </div>
                      <p className="text-xs text-slate-500 mt-1.5">
                        Passcode sent to <span className="text-slate-800 font-semibold">{otpEmail}</span>
                      </p>

                      {devCode && (
                        <div className="mt-3 p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800 flex items-center justify-between">
                          <span>Dev Mode Passcode:</span>
                          <span className="font-mono font-bold text-amber-900">{devCode}</span>
                        </div>
                      )}
                    </div>

                    <button
                      type="submit"
                      disabled={loading || otpCode.length < 6}
                      className="w-full py-3 px-4 bg-slate-950 hover:bg-black active:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-full font-semibold transition-all duration-150 flex items-center justify-center gap-2 text-sm shadow-md hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-slate-900"
                    >
                      {loading ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <span>Verify & Continue</span>
                      )}
                    </button>
                  </form>
                )}
              </div>
            )}

            {/* Footer Registration Link */}
            <div className="mt-6 pt-5 border-t border-slate-100 text-center">
              <p className="text-xs text-slate-600">
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  onClick={handleCreateAccountClick}
                  className="text-slate-950 font-bold hover:underline transition underline-offset-4"
                >
                  Register Now
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
