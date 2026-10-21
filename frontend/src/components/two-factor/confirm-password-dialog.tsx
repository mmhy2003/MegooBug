"use client";

import { useState, FormEvent } from "react";
import { X } from "lucide-react";
import { ApiError } from "@/lib/api";

interface ConfirmPasswordDialogProps {
  title: string;
  description?: string;
  confirmLabel: string;
  danger?: boolean;
  /** Optional extra text field shown above the password, e.g. a passkey name. */
  extraField?: { label: string; defaultValue: string };
  onConfirm: (password: string, extra: string) => Promise<void>;
  onClose: () => void;
}

/** Asks for the current password before a sensitive 2FA change. */
export function ConfirmPasswordDialog({
  title,
  description,
  confirmLabel,
  danger = false,
  extraField,
  onConfirm,
  onClose,
}: ConfirmPasswordDialogProps) {
  const [password, setPassword] = useState("");
  const [extra, setExtra] = useState(extraField?.defaultValue ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onConfirm(password, extra.trim());
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : "Something went wrong. Please try again.");
      if (err instanceof ApiError && err.message === "Password is incorrect") setPassword("");
      setBusy(false);
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-labelledby="confirm-password-title" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2 id="confirm-password-title">{title}</h2>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>
        {description && (
          <p className="text-muted" style={{ fontSize: "0.8125rem", marginBottom: "1rem" }}>
            {description}
          </p>
        )}
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {error && (
            <div className="auth-error" role="alert">
              {error}
            </div>
          )}
          {extraField && (
            <div className="form-group">
              <label htmlFor="confirm-extra" className="label">{extraField.label}</label>
              <input
                id="confirm-extra"
                className="input"
                value={extra}
                onChange={(e) => setExtra(e.target.value)}
                maxLength={100}
              />
            </div>
          )}
          <div className="form-group">
            <label htmlFor="confirm-password" className="label">Current password</label>
            <input
              id="confirm-password"
              type="password"
              className="input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              autoFocus={!extraField}
            />
          </div>
          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onClose}>Cancel</button>
            <button type="submit" className={`btn ${danger ? "btn-danger" : "btn-primary"}`} disabled={busy}>
              {busy ? "Please wait..." : confirmLabel}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
