"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { Bell, Check, CheckCheck, AlertTriangle, RefreshCw, X } from "lucide-react";
import { api } from "@/lib/api";

interface NotificationItem {
  id: string;
  type: string;
  title: string;
  body: string | null;
  is_read: boolean;
  issue_id: string | null;
  project_id: string | null;
  created_at: string;
}

interface NotificationResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Poll unread count every 30s
  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await api.get<{ count: number }>("/api/v1/notifications/unread-count");
      setUnreadCount(data.count);
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  // Close on click outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  async function loadNotifications() {
    setLoading(true);
    try {
      const data = await api.get<NotificationResponse>("/api/v1/notifications?limit=15");
      setNotifications(data.items);
      setUnreadCount(data.unread_count);
    } catch {}
    setLoading(false);
  }

  async function handleOpen() {
    setOpen(!open);
    if (!open) {
      await loadNotifications();
    }
  }

  async function markAsRead(id: string) {
    try {
      await api.patch(`/api/v1/notifications/${id}/read`);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {}
  }

  async function markAllRead() {
    try {
      await api.post("/api/v1/notifications/read-all");
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {}
  }

  function formatTime(iso: string) {
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "now";
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h`;
    return `${Math.floor(h / 24)}d`;
  }

  function getTypeIcon(type: string) {
    switch (type) {
      case "regression":
        return <RefreshCw size={14} style={{ color: "var(--accent-warning)" }} />;
      default:
        return <AlertTriangle size={14} style={{ color: "var(--accent-error)" }} />;
    }
  }

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        className="notification-btn"
        aria-label="Notifications"
        id="notification-bell"
        onClick={handleOpen}
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="notification-badge">
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          className="notification-dropdown"
          style={{
            position: "absolute",
            top: "calc(100% + 0.5rem)",
            right: 0,
            width: 380,
            maxHeight: 480,
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--shadow-elevated)",
            zIndex: 100,
            overflow: "hidden",
            animation: "fadeIn 150ms ease",
          }}
        >
          {/* Header */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0.75rem 1rem",
              borderBottom: "1px solid var(--border-color)",
            }}
          >
            <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>Notifications</span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {unreadCount > 0 && (
                <button
                  className="copy-btn"
                  style={{ fontSize: "0.6875rem" }}
                  onClick={markAllRead}
                >
                  <CheckCheck size={12} />
                  Mark all read
                </button>
              )}
              <button
                className="modal-close"
                onClick={() => setOpen(false)}
                style={{ padding: "0.125rem" }}
              >
                <X size={16} />
              </button>
            </div>
          </div>

          {/* Items */}
          <div style={{ overflowY: "auto", maxHeight: 400 }}>
            {loading && notifications.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-tertiary)" }}>
                Loading...
              </div>
            ) : notifications.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-tertiary)" }}>
                <Bell size={32} style={{ opacity: 0.3, marginBottom: "0.5rem" }} />
                <p>No notifications yet</p>
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    padding: "0.75rem 1rem",
                    borderBottom: "1px solid rgba(var(--accent-primary-rgb), 0.05)",
                    background: n.is_read ? "transparent" : "rgba(var(--accent-primary-rgb), 0.03)",
                    cursor: "pointer",
                    transition: "background 150ms",
                  }}
                  onClick={() => {
                    if (!n.is_read) markAsRead(n.id);
                  }}
                >
                  <div style={{ paddingTop: "0.125rem" }}>
                    {getTypeIcon(n.type)}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        fontWeight: n.is_read ? 400 : 600,
                        color: "var(--text-primary)",
                        marginBottom: "0.125rem",
                      }}
                    >
                      {n.title}
                    </div>
                    {n.body && (
                      <div
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--text-secondary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {n.body}
                      </div>
                    )}
                  </div>
                  <div
                    style={{
                      fontSize: "0.6875rem",
                      color: "var(--text-tertiary)",
                      whiteSpace: "nowrap",
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "0.375rem",
                    }}
                  >
                    {formatTime(n.created_at)}
                    {!n.is_read && (
                      <span
                        className="status-dot unresolved"
                        style={{ width: 6, height: 6, marginTop: 3 }}
                      />
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
