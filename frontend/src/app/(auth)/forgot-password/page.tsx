"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

type Step = "email" | "otp";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSendOtp(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setMessage(""); setLoading(true);
    const res = await fetch("/api/auth/forgot-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    setLoading(false);
    if (res.ok) {
      setMessage("A 6-digit code was sent to your email.");
      setStep("otp");
    } else {
      const d = await res.json();
      setError(d.error || "Failed to send code.");
    }
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (newPassword !== confirm) { setError("Passwords don't match"); return; }
    if (newPassword.length < 8) { setError("Password must be at least 8 characters"); return; }
    setLoading(true);
    const res = await fetch("/api/auth/reset-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, otp, newPassword }),
    });
    setLoading(false);
    if (res.ok) {
      setMessage("Password updated! Redirecting to login...");
      setTimeout(() => router.push("/login"), 2000);
    } else {
      const d = await res.json();
      setError(d.error || "Failed to reset password.");
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4"
      style={{ background: "var(--surface-0)" }}>
      <div className="absolute inset-0 pointer-events-none"
        style={{ background: "transparent" }} />

      <div className="relative w-full max-w-md animate-slide-up">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-4"
            style={{ background: "var(--accent)", boxShadow: "0 4px 0 #8a000e" }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <h1 className="text-3xl font-bold gradient-text">The Vault</h1>
        </div>

        <div className="glass rounded-2xl p-8">
          {/* Step indicator */}
          <div className="flex items-center gap-2 mb-6">
            {["email","otp"].map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                <div className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold"
                  style={{ background: step === s || (s === "email" && step === "otp") ? "rgba(99,102,241,0.3)" : "var(--surface-3)",
                    border: step === s ? "1px solid #6366f1" : "1px solid transparent",
                    color: step === s || (s === "email" && step === "otp") ? "#818cf8" : "var(--text-muted)" }}>
                  {s === "email" && step === "otp" ? "✓" : i + 1}
                </div>
                <span className="text-sm" style={{ color: step === s ? "var(--text-primary)" : "var(--text-muted)" }}>
                  {s === "email" ? "Enter email" : "Reset password"}
                </span>
                {i < 1 && <div className="flex-1 h-px mx-1" style={{ background: "var(--border)" }} />}
              </div>
            ))}
          </div>

          <h2 className="text-xl font-semibold mb-2">
            {step === "email" ? "Forgot your password?" : "Enter your reset code"}
          </h2>
          <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
            {step === "email"
              ? "We'll send a 6-digit code to your email address."
              : `Code sent to ${email}. Check your inbox.`}
          </p>

          {error && (
            <div className="mb-4 p-3 rounded-lg text-sm" style={{ background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.3)", color: "#f87171" }}>
              {error}
            </div>
          )}
          {message && (
            <div className="mb-4 p-3 rounded-lg text-sm" style={{ background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)", color: "#4ade80" }}>
              {message}
            </div>
          )}

          {step === "email" ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
                  Email address <span style={{ color: "#f87171" }}>*</span>
                </label>
                <input id="forgot-email" type="email" required className="input-field"
                  placeholder="you@example.com" value={email} onChange={e => setEmail(e.target.value)} />
              </div>
              <button id="send-otp-btn" type="submit" className="btn-primary w-full" disabled={loading}>
                {loading ? <span className="flex items-center justify-center gap-2"><span className="spinner" /> Sending...</span> : "Send reset code"}
              </button>
            </form>
          ) : (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
                  6-digit code <span style={{ color: "#f87171" }}>*</span>
                </label>
                <input id="otp-input" type="text" required maxLength={6} className="input-field text-center text-2xl font-mono tracking-widest"
                  placeholder="000000" value={otp} onChange={e => setOtp(e.target.value.replace(/\D/g, ""))} />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
                  New password <span style={{ color: "#f87171" }}>*</span>
                </label>
                <input id="new-password" type="password" required className="input-field"
                  placeholder="Min. 8 characters" value={newPassword} onChange={e => setNewPassword(e.target.value)} />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2" style={{ color: "var(--text-secondary)" }}>
                  Confirm password <span style={{ color: "#f87171" }}>*</span>
                </label>
                <input id="confirm-new-password" type="password" required className="input-field"
                  placeholder="Re-enter new password" value={confirm} onChange={e => setConfirm(e.target.value)} />
              </div>
              <button id="reset-password-btn" type="submit" className="btn-primary w-full" disabled={loading}>
                {loading ? <span className="flex items-center justify-center gap-2"><span className="spinner" /> Resetting...</span> : "Reset password"}
              </button>
              <button type="button" className="btn-ghost w-full" onClick={() => { setStep("email"); setError(""); setMessage(""); }}>
                ← Resend code
              </button>
            </form>
          )}

          <p className="text-center text-sm mt-6" style={{ color: "var(--text-muted)" }}>
            <Link href="/login" style={{ color: "var(--accent-light)" }}>← Back to sign in</Link>
          </p>
        </div>
      </div>
    </main>
  );
}
