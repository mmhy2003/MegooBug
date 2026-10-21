"use client";

import { useEffect, useState } from "react";
import { Fingerprint, Loader2, ShieldCheck, ShieldOff, Smartphone } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser } from "@/components/current-user-provider";
import { ConfirmPasswordDialog } from "@/components/two-factor/confirm-password-dialog";
import { TotpSetupModal } from "@/components/two-factor/totp-setup-modal";
import { defaultPasskeyName, passkeyErrorMessage, registerPasskey, type MfaMethod } from "@/lib/two-factor";

interface PasskeyInfo {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
}

interface TwoFactorStatus {
  enabled: boolean;
  required: boolean;
  methods: MfaMethod[];
  totp_enabled_at: string | null;
  passkeys: PasskeyInfo[];
}

type Dialog =
  | { kind: "add-passkey" }
  | { kind: "remove-passkey"; passkey: PasskeyInfo }
  | { kind: "remove-totp" }
  | null;

const BASE = "/api/v1/users/me/2fa";
const KEEP_ONE = "2FA is required for your account, so you must keep at least one method.";

function formatDate(iso: string | null) {
  if (!iso) return "never";
  return new Date(iso).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function Pill({ tone, children }: { tone: "success" | "warning" | "muted"; children: React.ReactNode }) {
  const color = tone === "success" ? "var(--accent-success)" : tone === "warning" ? "var(--accent-warning)" : "var(--text-secondary)";
  return (
    <span
      style={{
        padding: "0.125rem 0.625rem",
        borderRadius: "999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color,
        border: `1px solid color-mix(in srgb, ${color} 40%, transparent)`,
        background: `color-mix(in srgb, ${color} 10%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

function CardTitle({ icon: Icon, title, hint, children }: { icon: React.ElementType; title: string; hint: string; children?: React.ReactNode }) {
  return (
    <div style={{ flex: "1 1 280px", minWidth: 0 }}>
      <h2 style={{ fontSize: "1.125rem", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
        <Icon size={18} style={{ color: "var(--accent-primary)" }} />
        {title}
        {children}
      </h2>
      <p className="text-muted" style={{ fontSize: "0.8125rem" }}>{hint}</p>
    </div>
  );
}

/** Profile → Security: 2FA status, passkeys and the authenticator app. */
export function SecuritySettings() {
  const { user, setUser } = useCurrentUser();
  const [status, setStatus] = useState<TwoFactorStatus | null>(null);
  const [loadError, setLoadError] = useState("");
  const [dialog, setDialog] = useState<Dialog>(null);
  const [showTotpSetup, setShowTotpSetup] = useState(false);
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .get<TwoFactorStatus>(BASE)
      .then((data) => {
        if (!cancelled) setStatus(data);
      })
      .catch(() => {
        if (!cancelled) setLoadError("Couldn't load your security settings.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function apply(next: TwoFactorStatus) {
    setStatus(next);
    setUser({ ...user, mfa_methods: next.methods, mfa_required: next.required });
  }

  if (!status) {
    return (
      <div className="card" style={{ display: "flex", justifyContent: "center", padding: "2.5rem" }}>
        {loadError ? <span className="text-muted">{loadError}</span> : <Loader2 size={24} className="spin" style={{ color: "var(--text-tertiary)" }} />}
      </div>
    );
  }

  const hasTotp = status.methods.includes("totp");
  // Removing would leave a required user without any method
  const totpLocked = status.required && status.passkeys.length === 0;
  const passkeyLocked = status.required && !hasTotp && status.passkeys.length === 1;

  async function saveRename() {
    if (!renaming || !renaming.name.trim()) return;
    setActionError("");
    try {
      apply(await api.patch<TwoFactorStatus>(`${BASE}/passkeys/${renaming.id}`, { name: renaming.name.trim() }));
      setRenaming(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Couldn't rename the passkey.");
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Status */}
      <div className="card" style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
        <div
          aria-hidden="true"
          style={{
            width: 44,
            height: 44,
            borderRadius: "var(--radius-md)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
            color: status.enabled ? "var(--accent-success)" : "var(--text-secondary)",
            background: status.enabled
              ? "color-mix(in srgb, var(--accent-success) 12%, transparent)"
              : "var(--bg-input)",
          }}
        >
          {status.enabled ? <ShieldCheck size={22} /> : <ShieldOff size={22} />}
        </div>
        <CardTitle
          icon={() => null}
          title="Two-factor authentication"
          hint={
            status.enabled
              ? `After your password, you'll confirm it's you with ${hasTotp && status.passkeys.length ? "a passkey or your authenticator app" : hasTotp ? "your authenticator app" : "a passkey"}.${status.required ? " Because it's required, you need to keep at least one method." : ""}`
              : status.required
                ? "An admin requires 2FA for your account. Add a passkey or an authenticator app."
                : "Add a passkey or an authenticator app to protect your account beyond your password."
          }
        >
          <Pill tone={status.enabled ? "success" : "muted"}>{status.enabled ? "On" : "Off"}</Pill>
          {status.required && <Pill tone="warning">Required by admin</Pill>}
        </CardTitle>
      </div>

      {actionError && (
        <div className="auth-error" role="alert">{actionError}</div>
      )}

      {/* Passkeys */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <CardTitle icon={Fingerprint} title="Passkeys" hint="Sign in with your fingerprint, face, or a security key. You can add more than one." />
          <button className="btn btn-secondary" onClick={() => { setActionError(""); setDialog({ kind: "add-passkey" }); }}>
            Add passkey
          </button>
        </div>
        {status.passkeys.length === 0 && (
          <p className="text-muted" style={{ fontSize: "0.8125rem", paddingTop: "0.5rem" }}>No passkeys yet.</p>
        )}
        {status.passkeys.map((pk) => (
          <div
            key={pk.id}
            style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", padding: "0.875rem 0", borderTop: "1px solid var(--border-color)" }}
          >
            {renaming?.id === pk.id ? (
              <>
                <input
                  className="input"
                  aria-label="Passkey name"
                  value={renaming.name}
                  maxLength={100}
                  autoFocus
                  onChange={(e) => setRenaming({ id: pk.id, name: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveRename();
                    if (e.key === "Escape") setRenaming(null);
                  }}
                  style={{ flex: "1 1 220px" }}
                />
                <button className="btn btn-primary" onClick={saveRename}>Save</button>
                <button className="btn btn-ghost" onClick={() => setRenaming(null)}>Cancel</button>
              </>
            ) : (
              <>
                <div style={{ flex: "1 1 220px", minWidth: 0 }}>
                  <div style={{ fontSize: "0.875rem", fontWeight: 600, overflowWrap: "anywhere" }}>{pk.name}</div>
                  <div className="text-muted" style={{ fontSize: "0.8125rem" }}>
                    Added {formatDate(pk.created_at)} · Last used {formatDate(pk.last_used_at)}
                  </div>
                </div>
                <button className="btn btn-ghost" onClick={() => setRenaming({ id: pk.id, name: pk.name })}>
                  Rename
                </button>
                <button
                  className="btn btn-danger"
                  disabled={passkeyLocked}
                  title={passkeyLocked ? KEEP_ONE : undefined}
                  onClick={() => { setActionError(""); setDialog({ kind: "remove-passkey", passkey: pk }); }}
                >
                  Remove
                </button>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Authenticator app */}
      <div className="card" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
        <CardTitle
          icon={Smartphone}
          title="Authenticator app"
          hint={
            hasTotp
              ? `Codes from Google Authenticator, 1Password, Authy or similar. Set up ${formatDate(status.totp_enabled_at)}.`
              : "Use codes from Google Authenticator, 1Password, Authy or similar."
          }
        >
          {hasTotp && <Pill tone="success">Set up</Pill>}
        </CardTitle>
        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          {hasTotp ? (
            <>
              <button className="btn btn-ghost" onClick={() => { setActionError(""); setShowTotpSetup(true); }}>Replace</button>
              <button
                className="btn btn-danger"
                disabled={totpLocked}
                title={totpLocked ? KEEP_ONE : undefined}
                onClick={() => { setActionError(""); setDialog({ kind: "remove-totp" }); }}
              >
                Remove
              </button>
            </>
          ) : (
            <button className="btn btn-secondary" onClick={() => { setActionError(""); setShowTotpSetup(true); }}>Set up</button>
          )}
        </div>
      </div>

      {showTotpSetup && (
        <TotpSetupModal
          mode="profile"
          onDone={(next) => {
            apply(next as TwoFactorStatus);
            setShowTotpSetup(false);
          }}
          onClose={() => setShowTotpSetup(false)}
        />
      )}

      {dialog?.kind === "add-passkey" && (
        <ConfirmPasswordDialog
          title="Add a passkey"
          description="Confirm your password, then follow your browser's prompt."
          confirmLabel="Continue"
          extraField={{ label: "Passkey name", defaultValue: defaultPasskeyName() }}
          onConfirm={async (password, name) => {
            try {
              apply(
                await registerPasskey<TwoFactorStatus>(`${BASE}/passkeys/options`, `${BASE}/passkeys`, name, { password })
              );
            } catch (err) {
              if (err instanceof ApiError) throw err;
              throw new Error(passkeyErrorMessage(err, "Passkey setup failed"));
            }
            setDialog(null);
          }}
          onClose={() => setDialog(null)}
        />
      )}

      {dialog?.kind === "remove-passkey" && (
        <ConfirmPasswordDialog
          title="Remove passkey"
          description={`"${dialog.passkey.name}" will no longer be able to sign you in.`}
          confirmLabel="Remove"
          danger
          onConfirm={async (password) => {
            apply(await api.post<TwoFactorStatus>(`${BASE}/passkeys/${dialog.passkey.id}/remove`, { password }));
            setDialog(null);
          }}
          onClose={() => setDialog(null)}
        />
      )}

      {dialog?.kind === "remove-totp" && (
        <ConfirmPasswordDialog
          title="Remove authenticator app"
          description="Codes from your app will stop working for MegooBug."
          confirmLabel="Remove"
          danger
          onConfirm={async (password) => {
            apply(await api.post<TwoFactorStatus>(`${BASE}/totp/remove`, { password }));
            setDialog(null);
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </div>
  );
}
