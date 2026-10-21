"use client";

import { useEffect, useRef, useState, FormEvent } from "react";
import Image from "next/image";
import { ChevronRight, Fingerprint, ShieldAlert, Smartphone } from "lucide-react";
import { ApiError } from "@/lib/api";
import type { CurrentUser } from "@/components/current-user-provider";
import { TotpSetupModal } from "@/components/two-factor/totp-setup-modal";
import {
  SIGN_IN_EXPIRED,
  defaultPasskeyName,
  passkeyErrorMessage,
  registerPasskey,
  verifyLoginPasskey,
  verifyLoginTotp,
  type MfaChallenge,
} from "@/lib/two-factor";

type Step = "choose" | "totp" | "passkey" | "setup";

interface LoginSecondStepProps {
  challenge: MfaChallenge;
  onSuccess: (user: CurrentUser) => void;
  /** Back to the password form, optionally with a message to show there. */
  onRestart: (message?: string) => void;
}

const LOST_ACCESS = "Lost access? Ask an admin to reset your 2FA.";

function initialStep(challenge: MfaChallenge): Step {
  if (challenge.mfa_required === "setup") return "setup";
  if (challenge.methods.length > 1) return "choose";
  return challenge.methods[0] === "passkey" ? "passkey" : "totp";
}

function StepIcon({ children, tone = "primary" }: { children: React.ReactNode; tone?: "primary" | "warning" }) {
  return (
    <div className={`auth-step-icon ${tone === "warning" ? "warning" : ""}`} aria-hidden="true">
      {children}
    </div>
  );
}

/** The second login step: choose a method, enter a code, use a passkey, or set one up. */
export function LoginSecondStep({ challenge, onSuccess, onRestart }: LoginSecondStepProps) {
  const [step, setStep] = useState<Step>(() => initialStep(challenge));
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(step === "passkey");
  const [error, setError] = useState("");
  const [showTotpSetup, setShowTotpSetup] = useState(false);
  const autoStarted = useRef(false);

  const hasPasskey = challenge.methods.includes("passkey");
  const hasTotp = challenge.methods.includes("totp");

  function fail(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.message === SIGN_IN_EXPIRED) {
      onRestart(SIGN_IN_EXPIRED);
      return;
    }
    setError(err instanceof ApiError ? err.message : passkeyErrorMessage(err, fallback));
    setBusy(false);
  }

  function runPasskey() {
    setStep("passkey");
    setError("");
    setBusy(true);
    verifyLoginPasskey().then(onSuccess, (err) => fail(err, "Passkey verification failed"));
  }

  // A passkey-only user goes straight into the browser prompt.
  useEffect(() => {
    if (step !== "passkey" || autoStarted.current) return;
    autoStarted.current = true;
    verifyLoginPasskey().then(onSuccess, (err) => fail(err, "Passkey verification failed"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onSuccess(await verifyLoginTotp(code));
    } catch (err) {
      fail(err, "Incorrect code");
      setCode("");
    }
  }

  async function setupPasskey() {
    setBusy(true);
    setError("");
    try {
      onSuccess(
        await registerPasskey<CurrentUser>(
          "/api/v1/auth/2fa/setup/passkey/options",
          "/api/v1/auth/2fa/setup/passkey",
          defaultPasskeyName()
        )
      );
    } catch (err) {
      fail(err, "Passkey setup failed");
    }
  }

  const header = (title: string, text: string, icon?: React.ReactNode) => (
    <div className="auth-logo" style={{ marginBottom: "1.5rem" }}>
      {icon ?? (
        <Image src="/logo_new_transparent.png" alt="MegooBug logo" width={48} height={48} style={{ marginBottom: "0.5rem" }} />
      )}
      <h1 style={{ fontSize: "1.375rem" }}>{title}</h1>
      <p>{text}</p>
    </div>
  );

  const errorBox = error && (
    <div className="auth-error" role="alert" style={{ marginBottom: "1rem" }}>
      {error}
    </div>
  );

  return (
    <div className="auth-card">
      {step === "choose" && (
        <>
          {header("Verify it's you", `Signed in as ${challenge.email}. Choose how to finish signing in.`)}
          {errorBox}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <button type="button" className="auth-choice" onClick={runPasskey}>
              <span className="auth-choice-icon"><Fingerprint size={22} /></span>
              <span className="auth-choice-text">
                <strong>Use a passkey</strong>
                <span>Fingerprint, face, or security key</span>
              </span>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
            <button type="button" className="auth-choice" onClick={() => { setError(""); setStep("totp"); }}>
              <span className="auth-choice-icon"><Smartphone size={22} /></span>
              <span className="auth-choice-text">
                <strong>Use authenticator app</strong>
                <span>Enter the 6-digit code from your app</span>
              </span>
              <ChevronRight size={18} aria-hidden="true" />
            </button>
          </div>
        </>
      )}

      {step === "totp" && (
        <>
          {header(
            "Enter your code",
            "Open your authenticator app and enter the 6-digit code for MegooBug.",
            <StepIcon><Smartphone size={26} /></StepIcon>
          )}
          {errorBox}
          <form className="auth-form" onSubmit={submitCode}>
            <div className="form-group">
              <label htmlFor="login-totp-code" className="label">Verification code</label>
              <input
                id="login-totp-code"
                className="input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={7}
                placeholder="000000"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                required
                autoFocus
                style={{ fontFamily: "var(--font-mono)", fontSize: "1.375rem", letterSpacing: "0.35em", textAlign: "center", height: "3.25rem" }}
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={busy} style={{ width: "100%" }}>
              {busy ? "Verifying..." : "Verify"}
            </button>
          </form>
        </>
      )}

      {step === "passkey" && (
        <>
          {header(
            busy ? "Waiting for your passkey…" : "Use your passkey",
            "Follow the prompt from your browser or device to confirm it's you.",
            <StepIcon><Fingerprint size={30} /></StepIcon>
          )}
          {errorBox}
          {!busy && (
            <button type="button" className="btn btn-secondary" onClick={runPasskey} style={{ width: "100%" }}>
              Try again
            </button>
          )}
        </>
      )}

      {step === "setup" && (
        <>
          {header(
            "Set up two-factor authentication",
            "An admin requires 2FA for your account. Set up one method to continue.",
            <StepIcon tone="warning"><ShieldAlert size={26} /></StepIcon>
          )}
          {errorBox}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <button type="button" className="auth-choice" onClick={setupPasskey} disabled={busy}>
              <span className="auth-choice-icon"><Fingerprint size={22} /></span>
              <span className="auth-choice-text">
                <strong>Add a passkey</strong>
                <span>Uses this device&apos;s fingerprint, face, or a security key</span>
              </span>
            </button>
            <button type="button" className="auth-choice" onClick={() => { setError(""); setShowTotpSetup(true); }} disabled={busy}>
              <span className="auth-choice-icon"><Smartphone size={22} /></span>
              <span className="auth-choice-text">
                <strong>Use an authenticator app</strong>
                <span>Google Authenticator, 1Password, Authy…</span>
              </span>
            </button>
          </div>
        </>
      )}

      <div className="auth-footer" style={{ display: "flex", flexDirection: "column", gap: "0.625rem", alignItems: "center" }}>
        {step === "totp" && hasPasskey && (
          <button type="button" className="auth-link-btn" onClick={runPasskey}>Use a passkey instead</button>
        )}
        {step === "passkey" && hasTotp && (
          <button type="button" className="auth-link-btn" onClick={() => { setError(""); setBusy(false); setStep("totp"); }}>
            Use authenticator app instead
          </button>
        )}
        {(step === "totp" || step === "passkey") && <span>{LOST_ACCESS}</span>}
        <button type="button" className="auth-link-btn" onClick={() => onRestart()}>
          {step === "setup" ? "Sign out" : "Back to sign in"}
        </button>
      </div>

      {showTotpSetup && (
        <TotpSetupModal
          mode="login"
          onDone={(user) => onSuccess(user as CurrentUser)}
          onClose={() => setShowTotpSetup(false)}
        />
      )}
    </div>
  );
}
