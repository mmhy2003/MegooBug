"use client";

import { useState, useEffect, FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Bug, Eye, EyeOff, Loader2, ShieldCheck } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { ThemeToggle } from "@/components/theme-toggle";

interface InviteInfo {
  email: string;
  role: string;
  expires_at: string;
}

export default function RegisterPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") || "";

  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  // Invite info (pre-filled)
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("");
  const [validating, setValidating] = useState(true);
  const [invalidToken, setInvalidToken] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Validate the invite token on mount
  useEffect(() => {
    if (!token) {
      setInvalidToken(true);
      setValidating(false);
      return;
    }

    async function validateToken() {
      try {
        // We'll try to get invite info via the invites list or just show the form
        // Since there's no public endpoint to validate, just show the form
        // The actual validation happens on submit via accept-invite
        setValidating(false);
      } catch {
        setInvalidToken(true);
        setValidating(false);
      }
    }
    validateToken();
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await api.post("/api/v1/auth/accept-invite", {
        token,
        name,
        password,
      });
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  }

  if (!mounted) return null;

  if (validating) {
    return (
      <div className="auth-layout">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", color: "var(--text-secondary)" }}>
          <Loader2 size={24} className="spin" />
          Validating invite...
        </div>
      </div>
    );
  }

  if (invalidToken) {
    return (
      <div className="auth-layout">
        <div style={{ position: "fixed", top: "1.25rem", right: "1.25rem", zIndex: 50 }}>
          <ThemeToggle />
        </div>
        <div className="auth-card">
          <div className="auth-logo">
            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: "var(--radius-md)",
                  background: "linear-gradient(135deg, rgba(255,51,102,0.2), rgba(255,0,255,0.2))",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  border: "1px solid rgba(255,51,102,0.3)",
                }}
              >
                <Bug size={24} style={{ color: "var(--accent-error)" }} />
              </div>
            </div>
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>Invalid Invite</h1>
            <p className="text-muted" style={{ marginTop: "0.5rem" }}>
              This invite link is invalid, expired, or has already been used.
            </p>
          </div>
          <Link href="/login" className="btn btn-primary" style={{ width: "100%", justifyContent: "center", marginTop: "1.5rem" }}>
            Go to Login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-layout">
      <div style={{ position: "fixed", top: "1.25rem", right: "1.25rem", zIndex: 50 }}>
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="auth-logo">
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.75rem",
              marginBottom: "0.5rem",
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "var(--radius-md)",
                background:
                  "linear-gradient(135deg, rgba(0,240,255,0.2), rgba(255,0,255,0.2))",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px solid rgba(0,240,255,0.3)",
              }}
            >
              <ShieldCheck size={24} style={{ color: "var(--accent-primary)" }} />
            </div>
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 700 }}>
            You&apos;ve Been Invited
          </h1>
          <p className="text-muted" style={{ marginTop: "0.25rem" }}>
            Create your account to join MegooBug
          </p>
        </div>

        {error && <div className="auth-error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="register-name" className="label">
              Full Name
            </label>
            <input
              id="register-name"
              className="input"
              type="text"
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="register-password" className="label">
              Password
            </label>
            <div style={{ position: "relative" }}>
              <input
                id="register-password"
                className="input"
                type={showPassword ? "text" : "password"}
                placeholder="Min. 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={8}
                style={{ paddingRight: "2.5rem" }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                style={{
                  position: "absolute",
                  right: "0.75rem",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--text-tertiary)",
                  display: "flex",
                  padding: 0,
                }}
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            id="register-submit"
            disabled={loading}
            style={{ width: "100%", justifyContent: "center", marginTop: "0.5rem" }}
          >
            {loading ? (
              <Loader2 size={18} className="spin" />
            ) : (
              "Create Account"
            )}
          </button>
        </form>

        <p className="text-muted" style={{ marginTop: "1.5rem", textAlign: "center", fontSize: "0.8125rem" }}>
          Already have an account?{" "}
          <Link href="/login" style={{ color: "var(--accent-primary)" }}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
