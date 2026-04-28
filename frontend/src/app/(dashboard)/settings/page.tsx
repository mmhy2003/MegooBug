import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Settings — MegooBug",
  description: "Configure your MegooBug instance settings",
};

export default function SettingsPage() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Settings</h1>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {/* General Settings */}
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>
            General
          </h2>
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
                defaultValue="MegooBug"
              />
            </div>
            <div className="form-group">
              <label htmlFor="instance-url" className="label">Instance URL</label>
              <input
                id="instance-url"
                className="input"
                defaultValue="http://localhost:3000"
              />
            </div>
          </div>
        </div>

        {/* SMTP Settings */}
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>
            Email / SMTP
          </h2>
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
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-port" className="label">SMTP Port</label>
              <input
                id="smtp-port"
                className="input"
                type="number"
                defaultValue={587}
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-user" className="label">Username</label>
              <input id="smtp-user" className="input" placeholder="user@example.com" />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-pass" className="label">Password</label>
              <input
                id="smtp-pass"
                className="input"
                type="password"
                placeholder="••••••••"
              />
            </div>
            <div className="form-group">
              <label htmlFor="smtp-from" className="label">From Email</label>
              <input
                id="smtp-from"
                className="input"
                placeholder="noreply@example.com"
              />
            </div>
          </div>

          <div style={{ marginTop: "1rem", display: "flex", gap: "0.75rem" }}>
            <button className="btn btn-secondary" id="smtp-test-btn">
              Send Test Email
            </button>
            <button className="btn btn-primary" id="smtp-save-btn">
              Save
            </button>
          </div>
        </div>

        {/* Profile Settings */}
        <div className="card">
          <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>
            Profile
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "1rem",
            }}
          >
            <div className="form-group">
              <label htmlFor="profile-name" className="label">Name</label>
              <input id="profile-name" className="input" defaultValue="Admin" />
            </div>
            <div className="form-group">
              <label htmlFor="profile-email" className="label">Email</label>
              <input
                id="profile-email"
                className="input"
                defaultValue="admin@megoobug.local"
              />
            </div>
          </div>
          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-primary" id="profile-save-btn">
              Update Profile
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
