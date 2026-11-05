"use client";

import React, { useEffect, useRef, useState } from "react";
import { api, errorMessage, User } from "@/lib/api";
import { Mail, Lock, KeyRound, ShieldCheck, AlertCircle, Loader2, Eye, EyeOff, X } from "lucide-react";
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

  // Dismissible modal: Esc closes, overlay click closes, Tab is trapped inside,
  // and focus returns to the element that opened the dialog.
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

  // Handler for password login (accounts with a stored password; optional 2FA OTP)
  // New emails are NOT auto-registered here: the backend requires a verified OTP first.
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
        className="relative w-full max-w-md bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden p-6 text-slate-100"
      >
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close sign-in dialog"
            className="absolute right-3 top-3 p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition"
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        )}
        <div className="flex items-center gap-3 mb-5 pr-8">
          <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
            <ShieldCheck className="w-6 h-6" aria-hidden="true" />
          </div>
          <div>
            <h2 id="auth-dialog-title" className="text-xl font-bold">
              Research Studio
            </h2>
            <p className="text-sm text-slate-400">Secure Account Authentication</p>
          </div>
        </div>

        {/* Google Sign-In Button */}
        <button
          type="button"
          onClick={handleGoogleSignIn}
          disabled={loading}
          className="w-full mb-4 py-2.5 px-4 bg-white hover:bg-slate-100 text-slate-900 rounded-xl font-medium transition flex items-center justify-center gap-3 text-sm shadow-sm disabled:opacity-50"
        >
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin text-slate-600" />
          ) : (
            <svg className="w-4 h-4" viewBox="0 0 24 24" aria-hidden="true">
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

        {/* Divider */}
        <div className="relative flex items-center justify-center mb-4">
          <div className="border-t border-slate-800 w-full" />
          <span className="bg-slate-900 px-3 text-xs uppercase tracking-wider text-slate-500 font-medium absolute">
            or continue with email
          </span>
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
          <div
            role="alert"
            className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-center gap-2 text-sm text-red-400"
          >
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
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
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className="absolute right-3 top-3 text-slate-400 hover:text-slate-200"
                >
                  {showPassword ? (
                    <EyeOff className="w-4 h-4" aria-hidden="true" />
                  ) : (
                    <Eye className="w-4 h-4" aria-hidden="true" />
                  )}
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
              First time here?{" "}
              <button
                type="button"
                onClick={() => {
                  setAuthMode("otp");
                  setOtpStep("email");
                  setError(null);
                }}
                className="text-indigo-400 hover:underline font-medium"
              >
                Verify your email with a passcode
              </button>{" "}
              — new accounts are created only after OTP verification. Unknown emails cannot sign in with a password
              alone; add a fresh passcode below to set a password.
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
