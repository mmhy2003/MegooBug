"use client";

import { useEffect, useState, FormEvent } from "react";
import QRCode from "qrcode";
import { X, Copy, Check, AlertTriangle, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { groupSecret, type TotpSetup } from "@/lib/two-factor";

interface TotpSetupModalProps {
  /** "login": forced setup on the login page; "profile": Profile → Security. */
  mode: "login" | "profile";
  /** Called with the confirm response (the user in login mode, 2FA status in profile mode). */
  onDone: (result: unknown) => void;
  onClose: () => void;
}

const PATHS = {
  login: { begin: "/api/v1/auth/2fa/setup/totp", confirm: "/api/v1/auth/2fa/setup/totp/confirm" },
  profile: { begin: "/api/v1/users/me/2fa/totp", confirm: "/api/v1/users/me/2fa/totp/confirm" },
};

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

/** Authenticator-app setup: (password) → QR + key → confirm with a code. */
export function TotpSetupModal({ mode, onDone, onClose }: TotpSetupModalProps) {
  const paths = PATHS[mode];
  const [password, setPassword] = useState("");
  const [setup, setSetup] = useState<TotpSetup | null>(null);
  const [qr, setQr] = useState("");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(mode === "login");
  const [error, setError] = useState("");

  // Login mode starts right away: the pending sign-in already proved the password.
  useEffect(() => {
    if (mode !== "login") return;
    let cancelled = false;
    api
      .post<TotpSetup>(paths.begin)
      .then((data) => {
        if (!cancelled) setSetup(data);
      })
      .catch((err) => {
        if (!cancelled) setError(errorText(err));
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mode, paths.begin]);

  // The QR is drawn locally so the secret never leaves the browser.
  useEffect(() => {
    if (!setup) return;
    QRCode.toDataURL(setup.otpauth_uri, { margin: 1, width: 168 })
      .then(setQr)
      .catch(() => setQr(""));
  }, [setup]);

  async function handlePassword(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      setSetup(await api.post<TotpSetup>(paths.begin, { password }));
    } catch (err) {
      setError(errorText(err));
    }
    setBusy(false);
  }

  async function handleConfirm(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onDone(await api.post(paths.confirm, { code }));
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  async function copySecret() {
    if (!setup) return;
    try {
      await navigator.clipboard.writeText(setup.secret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-labelledby="totp-setup-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2 id="totp-setup-title">Set up authenticator app</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        <p className="text-muted" style={{ fontSize: "0.8125rem", marginBottom: "1.25rem" }}>
          Works with Google Authenticator, 1Password, Authy and others.
        </p>

        {error && (
          <div className="auth-error" role="alert" style={{ marginBottom: "1rem", display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <AlertTriangle size={14} /> {error}
          </div>
        )}

        {!setup && mode === "profile" && (
          <form onSubmit={handlePassword} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div className="form-group">
              <label htmlFor="totp-password" className="label">Current password</label>
              <input
                id="totp-password"
                type="password"
                className="input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                autoFocus
              />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "Checking..." : "Continue"}
              </button>
            </div>
          </form>
        )}

        {!setup && mode === "login" && busy && (
          <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
            <Loader2 size={28} className="spin" style={{ color: "var(--text-tertiary)" }} />
          </div>
        )}

        {setup && (
          <form onSubmit={handleConfirm} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div>
              <div style={{ fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.75rem" }}>
                1. Scan this QR code with your app
              </div>
              {qr ? (
                // eslint-disable-next-line @next/next/no-img-element -- local data: URL
                <img
                  src={qr}
                  alt="QR code for your authenticator app"
                  width={168}
                  height={168}
                  style={{ borderRadius: "var(--radius-md)", background: "#fff" }}
                />
              ) : (
                <div style={{ width: 168, height: 168 }} />
              )}
              <p className="text-muted" style={{ fontSize: "0.8125rem", margin: "0.75rem 0 0.5rem" }}>
                Can&apos;t scan? Enter this key instead:
              </p>
              <div className="token-display">
                <span style={{ flex: 1, fontFamily: "var(--font-mono)", letterSpacing: "0.08em" }}>
                  {groupSecret(setup.secret)}
                </span>
                <button type="button" className={`copy-btn ${copied ? "copied" : ""}`} onClick={copySecret}>
                  {copied ? <Check size={14} /> : <Copy size={14} />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="totp-confirm-code" className="label" style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                2. Enter the 6-digit code it shows
              </label>
              <input
                id="totp-confirm-code"
                className="input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                autoFocus
                style={{ fontFamily: "var(--font-mono)", fontSize: "1.25rem", letterSpacing: "0.35em", textAlign: "center" }}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "Verifying..." : "Verify and turn on"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
