"use client";

import { useState, FormEvent } from "react";
import { X, Mail, Copy, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";

interface Invite {
  id: string;
  email: string;
  role: string;
  token: string;
  expires_at: string;
}

interface Props {
  onClose: () => void;
  onCreated?: (invite: Invite) => void;
}

export function InviteUserModal({ onClose, onCreated }: Props) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("developer");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Invite | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const invite = await api.post<Invite>("/api/v1/invites", {
        email,
        role,
      });
      setCreated(invite);
      onCreated?.(invite);
    } catch (err) {
      if (err instanceof ApiError) {
        // Map API errors to user-friendly messages
        if (err.status === 409) {
          setError("This email address is already registered.");
        } else if (err.status === 422) {
          setError("Please enter a valid email address.");
        } else {
          setError(err.message || "Something went wrong. Please try again.");
        }
      } else {
        setError("Failed to create invite. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  }

  function getInviteLink() {
    if (!created) return "";
    const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
    return `${baseUrl}/register?token=${created.token}`;
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(getInviteLink());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{created ? "Invite Sent" : "Invite User"}</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {created ? (
          <div>
            <p style={{ color: "var(--text-secondary)", marginBottom: "1rem" }}>
              An invite has been created for <strong>{created.email}</strong>.
              Share the link below to let them register.
            </p>

            <label className="label">Invite Link</label>
            <div className="dsn-display">
              <span className="dsn-value">{getInviteLink()}</span>
              <button
                className={`copy-btn ${copied ? "copied" : ""}`}
                onClick={copyLink}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>

            <p className="text-muted" style={{ marginTop: "0.75rem", fontSize: "0.8125rem" }}>
              This link expires in 48 hours.
            </p>

            <div className="modal-actions">
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && (
              <div className="auth-error" style={{ marginBottom: "1rem" }}>
                {error}
              </div>
            )}

            <div className="form-group" style={{ marginBottom: "1rem" }}>
              <label htmlFor="invite-email" className="label">
                Email Address
              </label>
              <input
                id="invite-email"
                className="input"
                type="email"
                placeholder="user@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label htmlFor="invite-role" className="label">
                Role
              </label>
              <select
                id="invite-role"
                className="input"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="developer">Developer</option>
                <option value="viewer">Viewer</option>
              </select>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading || !email.trim()}
              >
                <Mail size={16} />
                {loading ? "Sending..." : "Send Invite"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
