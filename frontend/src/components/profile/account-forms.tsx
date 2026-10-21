"use client";

import { useState, FormEvent } from "react";
import { User, Lock, Check, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { useCurrentUser, type CurrentUser } from "@/components/current-user-provider";

type Status = { kind: "success" | "error"; text: string } | null;

const GENERIC_ERROR = "Something went wrong. Please try again.";

function errorText(err: unknown): string {
  return err instanceof ApiError ? err.message : GENERIC_ERROR;
}

function StatusLine({ status }: { status: Status }) {
  if (!status) return null;
  const ok = status.kind === "success";
  return (
    <span
      role={ok ? "status" : "alert"}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "0.375rem",
        fontSize: "0.8125rem",
        color: ok ? "var(--accent-success)" : "var(--accent-error)",
      }}
    >
      {ok ? <Check size={14} /> : <AlertTriangle size={14} />}
      {status.text}
    </span>
  );
}

function CardHeading({ icon: Icon, title, hint }: { icon: React.ElementType; title: string; hint: string }) {
  return (
    <div style={{ marginBottom: "1.25rem" }}>
      <h2 style={{ fontSize: "1.125rem", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <Icon size={18} style={{ color: "var(--accent-primary)" }} />
        {title}
      </h2>
      <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
        {hint}
      </p>
    </div>
  );
}

/** Account tab: personal details + password change. */
export function AccountForms() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <PersonalDetailsCard />
      <PasswordCard />
    </div>
  );
}

function PersonalDetailsCard() {
  const { user, setUser } = useCurrentUser();
  const [name, setName] = useState(user.name);
  const [email, setEmail] = useState(user.email);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setStatus({ kind: "error", text: "Name is required" });
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patch<CurrentUser>("/api/v1/users/me", {
        name: trimmed,
        email: email.trim(),
      });
      setUser(updated);
      setName(updated.name);
      setEmail(updated.email);
      setStatus({ kind: "success", text: "Profile updated" });
    } catch (err) {
      setStatus({ kind: "error", text: errorText(err) });
    }
    setSaving(false);
  }

  return (
    <div className="card">
      <CardHeading icon={User} title="Personal details" hint="Your name appears on issues, comments and team pages." />
      <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="form-group">
          <label htmlFor="profile-name" className="label">Full name</label>
          <input
            id="profile-name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={255}
            autoComplete="name"
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="profile-email" className="label">Email</label>
          <input
            id="profile-email"
            type="email"
            className="input"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            required
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? "Saving..." : "Save changes"}
          </button>
          <StatusLine status={status} />
        </div>
      </form>
    </div>
  );
}

function PasswordCard() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  async function handleUpdate(e: FormEvent) {
    e.preventDefault();
    setStatus(null);
    if (newPassword !== confirmPassword) {
      setStatus({ kind: "error", text: "Passwords don't match" });
      return;
    }
    setSaving(true);
    try {
      await api.patch("/api/v1/users/me/password", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setStatus({ kind: "success", text: "Password updated" });
    } catch (err) {
      setStatus({ kind: "error", text: errorText(err) });
    }
    setSaving(false);
  }

  return (
    <div className="card">
      <CardHeading
        icon={Lock}
        title="Password"
        hint="Use at least 8 characters. Changing it signs you out everywhere else. API keys keep working."
      />
      <form onSubmit={handleUpdate} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <div className="form-group">
          <label htmlFor="current-password" className="label">Current password</label>
          <input
            id="current-password"
            type="password"
            className="input"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="new-password" className="label">New password</label>
          <input
            id="new-password"
            type="password"
            className="input"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            maxLength={128}
            required
          />
        </div>
        <div className="form-group">
          <label htmlFor="confirm-password" className="label">Confirm new password</label>
          <input
            id="confirm-password"
            type="password"
            className="input"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
          <button type="submit" className="btn btn-secondary" disabled={saving}>
            {saving ? "Updating..." : "Update password"}
          </button>
          <StatusLine status={status} />
        </div>
      </form>
    </div>
  );
}
