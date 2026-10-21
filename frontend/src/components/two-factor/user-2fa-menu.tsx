"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, RotateCcw } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { menuPosition } from "@/lib/menu-position";
import type { MfaMethod } from "@/lib/two-factor";

export interface User2faFields {
  id: string;
  name: string;
  mfa_required: boolean;
  mfa_methods: MfaMethod[];
}

const MENU_WIDTH = 280;
// Tallest state (reset confirmation); used to decide whether to open upward
const MENU_HEIGHT = 190;

/** The 2FA pill shown in the admin Users table. */
export function TwoFactorBadge({ user }: { user: User2faFields }) {
  const methods = user.mfa_methods;
  if (methods.length > 0) {
    const label =
      methods.length > 1 ? "App + Passkey" : methods[0] === "passkey" ? "Passkey" : "App";
    return <span className="badge badge-success">On · {label}</span>;
  }
  if (user.mfa_required) {
    return <span className="badge badge-warning">Required · not set up</span>;
  }
  return <span className="badge">Off</span>;
}

interface User2faMenuProps<T extends User2faFields> {
  user: T;
  onUpdated: (user: T) => void;
}

/** Admin "2FA ▾" menu: require 2FA for a user, or reset their methods. */
export function User2faMenu<T extends User2faFields>({ user, onUpdated }: User2faMenuProps<T>) {
  const [open, setOpen] = useState(false);
  const [confirmingReset, setConfirmingReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // Fixed position: the table wrapper scrolls (overflow), which would clip an absolute menu
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setConfirmingReset(false);
      }
    }
    // A fixed menu would drift from its button on scroll/resize, so just close it
    function close() {
      setOpen(false);
      setConfirmingReset(false);
    }
    if (open) {
      document.addEventListener("mousedown", handleClick);
      window.addEventListener("scroll", close, true);
      window.addEventListener("resize", close);
    }
    return () => {
      document.removeEventListener("mousedown", handleClick);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  function toggle() {
    if (!open && buttonRef.current) {
      setPosition(
        menuPosition(
          buttonRef.current.getBoundingClientRect(),
          { width: MENU_WIDTH, height: MENU_HEIGHT },
          { width: window.innerWidth, height: window.innerHeight }
        )
      );
    }
    setOpen(!open);
    setConfirmingReset(false);
    setError("");
  }

  async function run(request: () => Promise<T>) {
    setBusy(true);
    setError("");
    try {
      onUpdated(await request());
      setConfirmingReset(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
    setBusy(false);
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        ref={buttonRef}
        className="btn btn-ghost"
        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={toggle}
      >
        2FA {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>

      {open && position && (
        <div
          role="menu"
          aria-label={`2FA options for ${user.name}`}
          className="notification-dropdown"
          style={{
            position: "fixed",
            top: position.top,
            left: position.left,
            zIndex: 100,
            width: MENU_WIDTH,
            padding: "0.375rem",
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-elevated)",
            whiteSpace: "normal",
          }}
        >
          <label
            role="menuitemcheckbox"
            aria-checked={user.mfa_required}
            style={{ display: "flex", alignItems: "center", gap: "0.75rem", padding: "0.625rem 0.75rem", cursor: busy ? "wait" : "pointer", borderRadius: "var(--radius-sm)" }}
          >
            <input
              type="checkbox"
              checked={user.mfa_required}
              disabled={busy}
              onChange={(e) =>
                run(() => api.patch<T>(`/api/v1/users/${user.id}/2fa-required`, { required: e.target.checked }))
              }
              style={{ width: 16, height: 16, accentColor: "var(--accent-primary)" }}
            />
            <span style={{ display: "flex", flexDirection: "column", fontSize: "0.875rem" }}>
              Require 2FA
              <span className="text-muted" style={{ fontSize: "0.75rem" }}>Must set it up at next sign-in</span>
            </span>
          </label>

          <div style={{ height: 1, background: "var(--border-color)", margin: "0.375rem 0" }} />

          {confirmingReset ? (
            <div style={{ padding: "0.5rem 0.75rem", display: "flex", flexDirection: "column", gap: "0.625rem" }}>
              <p style={{ fontSize: "0.8125rem" }}>
                This removes all of {user.name}&apos;s passkeys and authenticator app and signs them out.
              </p>
              <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                <button className="btn btn-ghost" style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }} onClick={() => setConfirmingReset(false)}>
                  Cancel
                </button>
                <button
                  className="btn btn-danger"
                  style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }}
                  disabled={busy}
                  onClick={() => run(() => api.post<T>(`/api/v1/users/${user.id}/2fa/reset`))}
                >
                  Reset 2FA
                </button>
              </div>
            </div>
          ) : (
            <button
              role="menuitem"
              className="btn btn-ghost btn-danger-text"
              style={{ width: "100%", justifyContent: "flex-start", padding: "0.625rem 0.75rem", fontSize: "0.875rem" }}
              disabled={busy || user.mfa_methods.length === 0}
              title={user.mfa_methods.length === 0 ? "No 2FA methods to reset" : undefined}
              onClick={() => setConfirmingReset(true)}
            >
              <RotateCcw size={14} />
              Reset 2FA…
            </button>
          )}

          {error && (
            <p role="alert" style={{ color: "var(--accent-error)", fontSize: "0.75rem", padding: "0.25rem 0.75rem" }}>
              {error}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
