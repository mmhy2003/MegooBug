"use client";

import { useState, useEffect, FormEvent } from "react";
import {
  Key, X, Copy, Check, AlertTriangle, Loader2, Plus, Trash2,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";

interface UserProfile {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface ApiToken {
  id: string;
  name: string;
  token_prefix: string;
  scopes: Record<string, unknown> | null;
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

interface CreatedToken extends ApiToken {
  raw_token: string;
}

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState("profile");
  const [profile, setProfile] = useState<UserProfile | null>(null);

  // General settings
  const [instanceName, setInstanceName] = useState("MegooBug");
  const [instanceUrl, setInstanceUrl] = useState("");

  // Profile
  const [profileName, setProfileName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileMsg, setProfileMsg] = useState("");

  // SMTP
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [smtpFrom, setSmtpFrom] = useState("");
  const [smtpSaving, setSmtpSaving] = useState(false);
  const [smtpMsg, setSmtpMsg] = useState("");

  // API Tokens
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [showCreateToken, setShowCreateToken] = useState(false);
  const [tokenName, setTokenName] = useState("");
  const [tokenExpiry, setTokenExpiry] = useState("");
  const [tokenCreating, setTokenCreating] = useState(false);
  const [createdToken, setCreatedToken] = useState<CreatedToken | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [tokenError, setTokenError] = useState("");

  useEffect(() => {
    loadProfile();
  }, []);

  useEffect(() => {
    if (activeTab === "apikeys") {
      loadTokens();
    }
    if (activeTab === "smtp") {
      loadSmtp();
    }
    if (activeTab === "general") {
      loadGeneral();
    }
  }, [activeTab]);

  async function loadProfile() {
    try {
      const user = await api.get<UserProfile>("/api/v1/users/me");
      setProfile(user);
      setProfileName(user.name);
      setProfileEmail(user.email);
    } catch {}
  }

  async function loadTokens() {
    setTokensLoading(true);
    try {
      const data = await api.get<ApiToken[]>("/api/v1/api-tokens");
      setTokens(data);
    } catch {}
    setTokensLoading(false);
  }

  async function loadSmtp() {
    try {
      const data = await api.get<{ key: string; value: Record<string, string> }>("/api/v1/settings/smtp");
      if (data.value) {
        setSmtpHost(data.value.host || "");
        setSmtpPort(data.value.port || "587");
        setSmtpUser(data.value.username || "");
        setSmtpPass(data.value.password || "");
        setSmtpFrom(data.value.from_email || "");
      }
    } catch {}
  }

  async function handleSmtpSave() {
    setSmtpSaving(true);
    setSmtpMsg("");
    try {
      await api.put("/api/v1/settings/smtp", {
        value: {
          host: smtpHost,
          port: smtpPort,
          username: smtpUser,
          password: smtpPass,
          from_email: smtpFrom,
        },
      });
      setSmtpMsg("SMTP settings saved successfully");
    } catch {
      setSmtpMsg("Failed to save SMTP settings");
    }
    setSmtpSaving(false);
  }

  const [smtpTesting, setSmtpTesting] = useState(false);
  const [testRecipient, setTestRecipient] = useState("");

  async function handleSmtpTest() {
    setSmtpTesting(true);
    setSmtpMsg("");
    try {
      const body: Record<string, string> = {};
      if (testRecipient.trim()) {
        body.recipient = testRecipient.trim();
      }
      const result = await api.post<{ ok: boolean; message?: string; error?: string }>(
        "/api/v1/settings/smtp/test",
        Object.keys(body).length > 0 ? body : undefined
      );
      if (result.ok) {
        setSmtpMsg(result.message || "Test email sent!");
      } else {
        setSmtpMsg(result.error || "SMTP test failed");
      }
    } catch {
      setSmtpMsg("Failed to send test email");
    }
    setSmtpTesting(false);
  }

  async function loadGeneral() {
    try {
      const data = await api.get<{ key: string; value: Record<string, string> }>("/api/v1/settings/general");
      if (data.value) {
        setInstanceName(data.value.instance_name || "MegooBug");
        setInstanceUrl(data.value.instance_url || "");
      }
    } catch {}
  }

  async function handleProfileSave(e: FormEvent) {
    e.preventDefault();
    setProfileSaving(true);
    setProfileMsg("");
    try {
      await api.patch("/api/v1/users/me", {
        name: profileName,
        email: profileEmail,
      });
      setProfileMsg("Profile updated successfully");
    } catch (err) {
      if (err instanceof ApiError) setProfileMsg(err.message);
    }
    setProfileSaving(false);
  }

  async function handleCreateToken(e: FormEvent) {
    e.preventDefault();
    setTokenCreating(true);
    setTokenError("");
    try {
      const result = await api.post<CreatedToken>("/api/v1/api-tokens", {
        name: tokenName,
        expires_in_days: tokenExpiry ? parseInt(tokenExpiry) : null,
      });
      setCreatedToken(result);
      setTokenName("");
      setTokenExpiry("");
      loadTokens();
    } catch (err) {
      if (err instanceof ApiError) setTokenError(err.message);
      else setTokenError("Failed to create token");
    }
    setTokenCreating(false);
  }

  async function handleRevokeToken(tokenId: string) {
    try {
      await api.delete(`/api/v1/api-tokens/${tokenId}`);
      setTokens((prev) => prev.filter((t) => t.id !== tokenId));
    } catch {}
  }

  async function copyToken() {
    if (!createdToken) return;
    try {
      await navigator.clipboard.writeText(createdToken.raw_token);
      setTokenCopied(true);
      setTimeout(() => setTokenCopied(false), 2000);
    } catch {}
  }

  function formatDate(iso: string | null) {
    if (!iso) return "—";
    return new Date(iso).toLocaleDateString();
  }

  const allTabs = [
    { key: "general", label: "General", roles: ["admin"] },
    { key: "smtp", label: "Email / SMTP", roles: ["admin"] },
    { key: "profile", label: "Profile", roles: ["admin", "developer", "viewer"] },
    { key: "apikeys", label: "API Keys", roles: ["admin", "developer"] },
  ];

  const userRole = profile?.role || "viewer";
  const visibleTabs = allTabs.filter((tab) => tab.roles.includes(userRole));

  // If active tab is not visible for this role, switch to the first visible tab
  const resolvedTab = visibleTabs.find((t) => t.key === activeTab)
    ? activeTab
    : visibleTabs[0]?.key || "profile";

  // Sync state if the resolved tab differs (e.g. after profile loads)
  useEffect(() => {
    if (resolvedTab !== activeTab) {
      setActiveTab(resolvedTab);
    }
  }, [resolvedTab, activeTab]);

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
      </div>

      <div className="tabs">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${resolvedTab === tab.key ? "active" : ""}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── General ── */}
      {activeTab === "general" && (
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>General</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "1rem",
            }}
          >
            <div className="form-group">
              <label htmlFor="instance-name" className="label">Instance Name</label>
              <input
                id="instance-name"
                className="input"
                value={instanceName}
                onChange={(e) => setInstanceName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="instance-url" className="label">Instance URL</label>
              <input
                id="instance-url"
                className="input"
                value={instanceUrl || (typeof window !== "undefined" ? window.location.origin : "")}
                onChange={(e) => setInstanceUrl(e.target.value)}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── SMTP ── */}
      {activeTab === "smtp" && (
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>Email / SMTP</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "1rem",
            }}
          >
            <div className="form-group">
              <label htmlFor="smtp-host" className="label">SMTP Host</label>
              <input
                id="smtp-host"
                className="input"
                placeholder="smtp.example.com"
                value={smtpHost}
                onChange={(e) => setSmtpHost(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-port" className="label">SMTP Port</label>
              <input
                id="smtp-port"
                className="input"
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-user" className="label">Username</label>
              <input
                id="smtp-user"
                className="input"
                placeholder="user@example.com"
                value={smtpUser}
                onChange={(e) => setSmtpUser(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-pass" className="label">Password</label>
              <input
                id="smtp-pass"
                className="input"
                type="password"
                placeholder="••••••••"
                value={smtpPass}
                onChange={(e) => setSmtpPass(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-from" className="label">From Email</label>
              <input
                id="smtp-from"
                className="input"
                placeholder="noreply@example.com"
                value={smtpFrom}
                onChange={(e) => setSmtpFrom(e.target.value)}
              />
            </div>
          </div>

          {/* Test Email Section */}
          <div
            style={{
              marginTop: "1.5rem",
              paddingTop: "1.25rem",
              borderTop: "1px solid var(--border-color)",
            }}
          >
            <h3 style={{ fontSize: "0.9375rem", marginBottom: "0.75rem" }}>
              Test Email
            </h3>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label htmlFor="smtp-test-recipient" className="label">
                Recipient Email
              </label>
              <input
                id="smtp-test-recipient"
                className="input"
                type="email"
                placeholder="Leave empty to use your account email"
                value={testRecipient}
                onChange={(e) => setTestRecipient(e.target.value)}
              />
              <span
                className="text-muted"
                style={{ fontSize: "0.75rem", marginTop: "0.25rem", display: "block" }}
              >
                If empty, the test email will be sent to your account email.
              </span>
            </div>
            <div
              style={{
                marginTop: "0.75rem",
                display: "flex",
                gap: "0.75rem",
                alignItems: "center",
              }}
            >
              <button
                className="btn btn-secondary"
                id="smtp-test-btn"
                onClick={handleSmtpTest}
                disabled={smtpTesting}
              >
                {smtpTesting ? "Sending..." : "Send Test Email"}
              </button>
              <button
                className="btn btn-primary"
                id="smtp-save-btn"
                onClick={handleSmtpSave}
                disabled={smtpSaving}
              >
                {smtpSaving ? "Saving..." : "Save Settings"}
              </button>
              {smtpMsg && (
                <span
                  style={{
                    fontSize: "0.8125rem",
                    color: smtpMsg.includes("sent") || smtpMsg.includes("success")
                      ? "var(--accent-success)"
                      : "var(--accent-error)",
                  }}
                >
                  {smtpMsg}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── Profile ── */}
      {activeTab === "profile" && (
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>Profile</h2>
          <form onSubmit={handleProfileSave}>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "1rem",
              }}
            >
              <div className="form-group">
                <label htmlFor="profile-name" className="label">Name</label>
                <input
                  id="profile-name"
                  className="input"
                  value={profileName}
                  onChange={(e) => setProfileName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="profile-email" className="label">Email</label>
                <input
                  id="profile-email"
                  className="input"
                  value={profileEmail}
                  onChange={(e) => setProfileEmail(e.target.value)}
                />
              </div>
            </div>
            {profileMsg && (
              <p
                style={{
                  marginTop: "0.75rem",
                  fontSize: "0.8125rem",
                  color: profileMsg.includes("success")
                    ? "var(--accent-success)"
                    : "var(--accent-error)",
                }}
              >
                {profileMsg}
              </p>
            )}
            <div style={{ marginTop: "1rem" }}>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={profileSaving}
              >
                {profileSaving ? "Saving..." : "Update Profile"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── API Keys ── */}
      {activeTab === "apikeys" && (
        <div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
              API tokens are used to authenticate with the Sentry CLI and MCP server.
            </p>
            <button
              className="btn btn-primary"
              onClick={() => { setShowCreateToken(true); setCreatedToken(null); }}
            >
              <Plus size={16} />
              Create Token
            </button>
          </div>

          {tokensLoading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
              <Loader2 size={24} className="spin" style={{ color: "var(--text-tertiary)" }} />
            </div>
          ) : tokens.length === 0 ? (
            <div className="card empty-state">
              <Key size={48} className="empty-state-icon" />
              <h3 style={{ marginBottom: "0.5rem" }}>No API tokens</h3>
              <p className="text-muted">Create a token to integrate with Sentry CLI or MCP.</p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Token</th>
                    <th>Last Used</th>
                    <th>Created</th>
                    <th>Expires</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {tokens.map((token) => (
                    <tr key={token.id}>
                      <td style={{ fontWeight: 500 }}>{token.name}</td>
                      <td>
                        <span className="text-mono" style={{ fontSize: "0.8125rem" }}>
                          {token.token_prefix}••••••••
                        </span>
                      </td>
                      <td className="text-muted">{formatDate(token.last_used_at)}</td>
                      <td className="text-muted">{formatDate(token.created_at)}</td>
                      <td className="text-muted">{formatDate(token.expires_at)}</td>
                      <td>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", color: "var(--accent-error)" }}
                          onClick={() => handleRevokeToken(token.id)}
                        >
                          <Trash2 size={14} />
                          Revoke
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create Token Modal */}
      {showCreateToken && (
        <div className="modal-overlay" onClick={() => { setShowCreateToken(false); setCreatedToken(null); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{createdToken ? "Token Created" : "Create API Token"}</h2>
              <button
                className="modal-close"
                onClick={() => { setShowCreateToken(false); setCreatedToken(null); }}
              >
                <X size={20} />
              </button>
            </div>

            {createdToken ? (
              <div>
                <div className="token-warning">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <AlertTriangle size={16} style={{ color: "var(--accent-warning)" }} />
                    <strong style={{ fontSize: "0.875rem", color: "var(--accent-warning)" }}>
                      Copy your token now
                    </strong>
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    This is the only time this token will be displayed. Store it securely.
                  </p>
                  <div className="token-display">
                    <span style={{ flex: 1, wordBreak: "break-all" }}>
                      {createdToken.raw_token}
                    </span>
                    <button
                      className={`copy-btn ${tokenCopied ? "copied" : ""}`}
                      onClick={copyToken}
                    >
                      {tokenCopied ? <Check size={14} /> : <Copy size={14} />}
                      {tokenCopied ? "Copied" : "Copy"}
                    </button>
                  </div>
                </div>
                <div className="modal-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() => { setShowCreateToken(false); setCreatedToken(null); }}
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleCreateToken}>
                {tokenError && (
                  <div className="auth-error" style={{ marginBottom: "1rem" }}>
                    {tokenError}
                  </div>
                )}
                <div className="form-group" style={{ marginBottom: "1rem" }}>
                  <label htmlFor="token-name" className="label">Token Name</label>
                  <input
                    id="token-name"
                    className="input"
                    placeholder="e.g. CI/CD Token"
                    value={tokenName}
                    onChange={(e) => setTokenName(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="token-expiry" className="label">
                    Expires In (days) <span className="text-muted" style={{ fontWeight: 400 }}>— optional</span>
                  </label>
                  <input
                    id="token-expiry"
                    className="input"
                    type="number"
                    min={1}
                    max={365}
                    placeholder="Leave empty for no expiry"
                    value={tokenExpiry}
                    onChange={(e) => setTokenExpiry(e.target.value)}
                  />
                </div>
                <div className="modal-actions">
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => setShowCreateToken(false)}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={tokenCreating || !tokenName.trim()}
                  >
                    {tokenCreating ? "Creating..." : "Create Token"}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
