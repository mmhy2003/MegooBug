"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useCurrentUser } from "@/components/current-user-provider";
import { api } from "@/lib/api";

// Instance-wide settings (admin only). Personal settings live on /profile.
export default function SettingsPage() {
  const router = useRouter();
  const { user } = useCurrentUser();
  const isAdmin = user.role === "admin";
  const [activeTab, setActiveTab] = useState("general");

  // General settings
  const [instanceName, setInstanceName] = useState("MegooBug");
  const [instanceUrl, setInstanceUrl] = useState("");

  // SMTP
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUser, setSmtpUser] = useState("");
  const [smtpPass, setSmtpPass] = useState("");
  const [smtpFrom, setSmtpFrom] = useState("");
  const [smtpSaving, setSmtpSaving] = useState(false);
  const [smtpMsg, setSmtpMsg] = useState("");

  useEffect(() => {
    if (!isAdmin) {
      router.replace("/profile");
    }
  }, [isAdmin, router]);

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


  useEffect(() => {
    if (!isAdmin) return;
    if (activeTab === "smtp") {
      loadSmtp();
    }
    if (activeTab === "general") {
      loadGeneral();
    }
  }, [activeTab, isAdmin]);

  const tabs = [
    { key: "general", label: "General" },
    { key: "smtp", label: "Email / SMTP" },
  ];

  // Non-admins are being redirected to /profile
  if (!isAdmin) return null;

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
      </div>

      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={`tab ${activeTab === tab.key ? "active" : ""}`}
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
    </div>
  );
}
