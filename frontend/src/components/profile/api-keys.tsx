"use client";

import { useState, useEffect, FormEvent } from "react";
import { AlertTriangle, Check, Copy, Key, Loader2, Plus, Trash2, X } from "lucide-react";
import { api, ApiError } from "@/lib/api";

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

/** Personal API tokens: list, create (shown once), revoke. */
export function ApiKeys() {
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(true);
  const [showCreateToken, setShowCreateToken] = useState(false);
  const [tokenName, setTokenName] = useState("");
  const [tokenExpiry, setTokenExpiry] = useState("");
  const [tokenCreating, setTokenCreating] = useState(false);
  const [createdToken, setCreatedToken] = useState<CreatedToken | null>(null);
  const [tokenCopied, setTokenCopied] = useState(false);
  const [tokenError, setTokenError] = useState("");

  async function loadTokens() {
    setTokensLoading(true);
    try {
      const data = await api.get<ApiToken[]>("/api/v1/api-tokens");
      setTokens(data);
    } catch {}
    setTokensLoading(false);
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

  useEffect(() => {
    let cancelled = false;
    api
      .get<ApiToken[]>("/api/v1/api-tokens")
      .then((data) => {
        if (!cancelled) setTokens(data);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setTokensLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
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
    </>
  );
}
