"use client";

import { useState, useEffect } from "react";
import { AlertTriangle, BellRing, Bug, Check, Loader2, RefreshCw, UserCheck } from "lucide-react";
import { api } from "@/lib/api";

/** In-app / email notification toggles per event type (auto-saved). */
export function NotificationPreferences() {
  interface NotifPref {
    inapp: boolean;
    email: boolean;
  }
  interface NotifPreferences {
    new_issue: NotifPref;
    regression: NotifPref;
    assigned: NotifPref;
  }
  const defaultPrefs: NotifPreferences = {
    new_issue: { inapp: true, email: true },
    regression: { inapp: true, email: true },
    assigned: { inapp: true, email: true },
  };
  const [notifPrefs, setNotifPrefs] = useState<NotifPreferences>(defaultPrefs);
  const [notifLoading, setNotifLoading] = useState(true);
  const [notifSaving, setNotifSaving] = useState(false);
  const [notifMsg, setNotifMsg] = useState("");

  async function handleTogglePref(
    key: keyof NotifPreferences,
    channel: "inapp" | "email"
  ) {
    const newPrefs = { ...notifPrefs };
    newPrefs[key] = { ...newPrefs[key], [channel]: !newPrefs[key][channel] };
    setNotifPrefs(newPrefs);
    setNotifSaving(true);
    setNotifMsg("");
    try {
      await api.put("/api/v1/users/me/notification-preferences", {
        preferences: newPrefs,
      });
      setNotifMsg("Preferences saved");
      setTimeout(() => setNotifMsg(""), 2000);
    } catch {
      // Revert on failure
      setNotifPrefs(notifPrefs);
      setNotifMsg("Failed to save preferences");
    }
    setNotifSaving(false);
  }

  useEffect(() => {
    let cancelled = false;
    api
      .get<{ preferences: NotifPreferences }>("/api/v1/users/me/notification-preferences")
      .then((data) => {
        if (!cancelled && data.preferences) {
          setNotifPrefs((prev) => ({ ...prev, ...data.preferences }));
        }
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setNotifLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="card">
      <div style={{ marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "1.125rem", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <BellRing size={20} style={{ color: "var(--accent-primary)" }} />
          Notification Preferences
        </h2>
        <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
          Control which notifications you receive. Changes are saved automatically.
        </p>
      </div>

      {notifLoading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
          <Loader2 size={24} className="spin" style={{ color: "var(--text-tertiary)" }} />
        </div>
      ) : (
        <div>
          {/* Header row */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 100px 100px",
              gap: "1rem",
              padding: "0.75rem 1rem",
              borderBottom: "1px solid var(--border-color)",
              fontSize: "0.6875rem",
              fontWeight: 600,
              color: "var(--text-tertiary)",
              textTransform: "uppercase" as const,
              letterSpacing: "0.05em",
            }}
          >
            <span>Event Type</span>
            <span style={{ textAlign: "center" }}>In-App</span>
            <span style={{ textAlign: "center" }}>Email</span>
          </div>

          {/* Notification rows */}
          {([
            {
              key: "new_issue" as const,
              label: "New Issues",
              description: "When a new error or issue is first detected in your projects",
              icon: <Bug size={18} />,
              color: "var(--accent-error)",
            },
            {
              key: "regression" as const,
              label: "Regressions",
              description: "When a previously resolved issue reappears with new events",
              icon: <RefreshCw size={18} />,
              color: "var(--accent-warning)",
            },
            {
              key: "assigned" as const,
              label: "Project Assignment",
              description: "When you are added to a project by an admin",
              icon: <UserCheck size={18} />,
              color: "var(--accent-primary)",
            },
          ]).map((item) => (
            <div
              key={item.key}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 100px 100px",
                gap: "1rem",
                padding: "1rem",
                borderBottom: "1px solid var(--border-color)",
                alignItems: "center",
                transition: "background 150ms",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 36,
                    height: 36,
                    borderRadius: "var(--radius-sm)",
                    background: `color-mix(in srgb, ${item.color} 12%, transparent)`,
                    color: item.color,
                    flexShrink: 0,
                  }}
                >
                  {item.icon}
                </div>
                <div>
                  <div style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-primary)" }}>
                    {item.label}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.125rem" }}>
                    {item.description}
                  </div>
                </div>
              </div>

              {/* In-App Toggle */}
              <div style={{ display: "flex", justifyContent: "center" }}>
                <button
                  className={`notif-toggle ${notifPrefs[item.key].inapp ? "active" : ""}`}
                  onClick={() => handleTogglePref(item.key, "inapp")}
                  disabled={notifSaving}
                  aria-label={`Toggle in-app ${item.label}`}
                  id={`notif-toggle-inapp-${item.key}`}
                  style={{
                    width: 44,
                    height: 24,
                    borderRadius: 12,
                    border: "1px solid var(--border-color)",
                    background: notifPrefs[item.key].inapp
                      ? "var(--accent-primary)"
                      : "var(--bg-tertiary)",
                    cursor: "pointer",
                    position: "relative" as const,
                    transition: "background 200ms, border-color 200ms",
                    padding: 0,
                  }}
                >
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: "50%",
                      background: "#fff",
                      position: "absolute" as const,
                      top: 2,
                      left: notifPrefs[item.key].inapp ? 22 : 2,
                      transition: "left 200ms cubic-bezier(0.4, 0, 0.2, 1)",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                    }}
                  />
                </button>
              </div>

              {/* Email Toggle */}
              <div style={{ display: "flex", justifyContent: "center" }}>
                <button
                  className={`notif-toggle ${notifPrefs[item.key].email ? "active" : ""}`}
                  onClick={() => handleTogglePref(item.key, "email")}
                  disabled={notifSaving}
                  aria-label={`Toggle email ${item.label}`}
                  id={`notif-toggle-email-${item.key}`}
                  style={{
                    width: 44,
                    height: 24,
                    borderRadius: 12,
                    border: "1px solid var(--border-color)",
                    background: notifPrefs[item.key].email
                      ? "var(--accent-primary)"
                      : "var(--bg-tertiary)",
                    cursor: "pointer",
                    position: "relative" as const,
                    transition: "background 200ms, border-color 200ms",
                    padding: 0,
                  }}
                >
                  <div
                    style={{
                      width: 18,
                      height: 18,
                      borderRadius: "50%",
                      background: "#fff",
                      position: "absolute" as const,
                      top: 2,
                      left: notifPrefs[item.key].email ? 22 : 2,
                      transition: "left 200ms cubic-bezier(0.4, 0, 0.2, 1)",
                      boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
                    }}
                  />
                </button>
              </div>
            </div>
          ))}

          {/* Status message */}
          {notifMsg && (
            <div
              style={{
                padding: "0.75rem 1rem",
                fontSize: "0.8125rem",
                color: notifMsg.includes("saved") || notifMsg.includes("success")
                  ? "var(--accent-success)"
                  : "var(--accent-error)",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              {notifMsg.includes("saved") ? <Check size={14} /> : <AlertTriangle size={14} />}
              {notifMsg}
            </div>
          )}

          {/* Helper text */}
          <div
            style={{
              padding: "1rem",
              fontSize: "0.75rem",
              color: "var(--text-tertiary)",
              borderTop: "1px solid var(--border-color)",
              lineHeight: 1.5,
            }}
          >
            <strong>In-App</strong> notifications appear in the bell icon in the header.
            <strong> Email</strong> notifications are sent to your account email when SMTP is configured.
            Per-project notification settings can also be configured in project settings.
          </div>
        </div>
      )}
    </div>
  );
}
