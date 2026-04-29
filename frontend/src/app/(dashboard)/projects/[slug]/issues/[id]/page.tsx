"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronRight, Loader2, Clock, Hash, AlertTriangle,
  CheckCircle, XCircle, Eye,
} from "lucide-react";
import { api } from "@/lib/api";

interface Issue {
  id: string;
  project_id: string;
  title: string;
  fingerprint: string;
  status: string;
  level: string;
  first_seen: string;
  last_seen: string;
  event_count: number;
  metadata_: Record<string, unknown> | null;
}

interface EventItem {
  id: string;
  issue_id: string;
  project_id: string;
  event_id: string;
  data: Record<string, unknown>;
  timestamp: string;
  received_at: string;
}

interface EventList {
  items: EventItem[];
  total: number;
}

interface StackFrame {
  filename?: string;
  function?: string;
  lineno?: number;
  colno?: number;
  module?: string;
  abs_path?: string;
}

interface ExceptionValue {
  type?: string;
  value?: string;
  stacktrace?: {
    frames?: StackFrame[];
  };
}

export default function IssueDetailPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id } = use(params);
  const router = useRouter();

  const [issue, setIssue] = useState<Issue | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("stacktrace");
  const [titleExpanded, setTitleExpanded] = useState(false);
  const [userRole, setUserRole] = useState<string>("");

  useEffect(() => {
    async function load() {
      try {
        const [issueData, eventsData, me] = await Promise.all([
          api.get<Issue>(`/api/v1/issues/${id}`),
          api.get<EventList>(`/api/v1/issues/${id}/events?limit=20`),
          api.get<{ role: string }>("/api/v1/users/me"),
        ]);
        setIssue(issueData);
        setEvents(eventsData.items);
        setUserRole(me.role);
      } catch {
        router.push(`/projects/${slug}`);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id, slug, router]);

  async function updateStatus(newStatus: string) {
    if (!issue) return;
    try {
      const updated = await api.patch<Issue>(`/api/v1/issues/${id}`, {
        status: newStatus,
      });
      setIssue(updated);
    } catch {}
  }

  function formatTime(iso: string) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString();
  }

  function formatRelativeTime(iso: string) {
    if (!iso) return "—";
    const diff = Date.now() - new Date(iso).getTime();
    const m = Math.floor(diff / 60000);
    if (m < 1) return "just now";
    if (m < 60) return `${m}m ago`;
    const h = Math.floor(m / 60);
    if (h < 24) return `${h}h ago`;
    return `${Math.floor(h / 24)}d ago`;
  }

  function getLevelBadgeClass(level: string) {
    switch (level) {
      case "fatal": return "badge badge-error badge-pulse";
      case "error": return "badge badge-error";
      case "warning": return "badge badge-warning";
      default: return "badge badge-info";
    }
  }

  function getStatusBadgeClass(status: string) {
    switch (status) {
      case "resolved": return "badge badge-success";
      case "ignored": return "badge badge-warning";
      default: return "badge badge-error";
    }
  }

  // Extract exception info from the latest event
  // Handles: exception.values[], logentry, and threads.values[].stacktrace
  function getExceptions(): ExceptionValue[] {
    if (events.length === 0) return [];
    const latestEvent = events[0];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = latestEvent.data as any;

    // 1. Standard exception interface
    const exc = data?.exception;
    if (exc?.values && exc.values.length > 0) {
      return exc.values as ExceptionValue[];
    }

    // 2. Build synthetic exception from logentry + threads
    const results: ExceptionValue[] = [];

    // Extract logentry as the error "header"
    const logentry = data?.logentry;
    const message = data?.message;
    let errorTitle = "";
    let errorValue = "";

    if (logentry) {
      errorTitle = logentry.message || "Log Message";
      errorValue = logentry.formatted || logentry.message || "";
    } else if (typeof message === "string") {
      errorTitle = "Message";
      errorValue = message;
    } else if (message?.formatted) {
      errorTitle = "Message";
      errorValue = message.formatted;
    }

    // Extract stacktrace from threads
    let stacktrace: { frames?: StackFrame[] } | undefined;
    const threads = data?.threads;
    if (threads) {
      const threadValues = Array.isArray(threads) ? threads : threads.values;
      if (Array.isArray(threadValues)) {
        // Find the crashed thread, or the current thread, or just the first with frames
        const crashedThread =
          threadValues.find((t: { crashed?: boolean }) => t.crashed) ||
          threadValues.find((t: { current?: boolean }) => t.current) ||
          threadValues.find(
            (t: { stacktrace?: { frames?: StackFrame[] } }) =>
              t.stacktrace?.frames && t.stacktrace.frames.length > 0
          );
        if (crashedThread?.stacktrace?.frames) {
          stacktrace = crashedThread.stacktrace;
        }
      }
    }

    if (errorTitle || errorValue || stacktrace) {
      results.push({
        type: errorTitle || data?.logger || "Error",
        value: errorValue,
        stacktrace,
      });
    }

    return results;
  }

  // Extract tags/context from latest event
  function getEventMeta() {
    if (events.length === 0) return {};
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const data = events[0].data as any;

    // Build a display message from logentry or message
    let displayMessage = data?.message;
    if (data?.logentry?.formatted) {
      displayMessage = data.logentry.formatted;
    } else if (data?.logentry?.message) {
      displayMessage = data.logentry.message;
    }
    if (typeof displayMessage === "object") {
      displayMessage = displayMessage?.formatted || displayMessage?.message || "";
    }

    return {
      sdk: data?.sdk,
      contexts: data?.contexts,
      tags: data?.tags,
      message: displayMessage,
      logger: data?.logger,
      environment: data?.environment,
      server_name: data?.server_name,
      release: data?.release,
    };
  }

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
        <Loader2 size={32} className="spin" style={{ color: "var(--text-tertiary)" }} />
      </div>
    );
  }

  if (!issue) return null;

  const exceptions = getExceptions();
  const meta = getEventMeta();

  return (
    <div>
      {/* Breadcrumbs */}
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <ChevronRight size={14} className="separator" />
        <Link href={`/projects/${slug}`}>{slug}</Link>
        <ChevronRight size={14} className="separator" />
        <span style={{ color: "var(--text-primary)" }}>Issue</span>
      </div>

      {/* Issue Header */}
      <div className="issue-header">
        <div style={{ flex: 1, minWidth: 0 }}>
          <h1
            style={{
              fontSize: "1.25rem",
              fontWeight: 600,
              marginBottom: "0.5rem",
              wordBreak: "break-word",
              ...(titleExpanded
                ? {}
                : {
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical" as const,
                    overflow: "hidden",
                  }),
            }}
            title={issue.title}
          >
            {issue.title}
          </h1>
          {issue.title.length > 120 && (
            <button
              onClick={() => setTitleExpanded(!titleExpanded)}
              style={{
                background: "none",
                border: "none",
                color: "var(--accent-primary)",
                cursor: "pointer",
                fontSize: "0.75rem",
                padding: 0,
                marginBottom: "0.75rem",
              }}
            >
              {titleExpanded ? "Show less" : "Show full title"}
            </button>
          )}
          <div className="issue-meta">
            <span className={getLevelBadgeClass(issue.level)}>{issue.level}</span>
            <span className={getStatusBadgeClass(issue.status)}>{issue.status}</span>
            <span className="issue-meta-item">
              <Hash size={14} />
              {issue.event_count} events
            </span>
            <span className="issue-meta-item">
              <Clock size={14} />
              First: {formatRelativeTime(issue.first_seen)}
            </span>
            <span className="issue-meta-item">
              <Clock size={14} />
              Last: {formatRelativeTime(issue.last_seen)}
            </span>
          </div>
        </div>

        {/* Action buttons — only for admin and developer */}
        {(userRole === "admin" || userRole === "developer") && (
          <div className="issue-actions">
            {issue.status !== "resolved" && (
              <button className="btn btn-primary" onClick={() => updateStatus("resolved")}>
                <CheckCircle size={16} />
                Resolve
              </button>
            )}
            {issue.status === "resolved" && (
              <button className="btn btn-secondary" onClick={() => updateStatus("unresolved")}>
                <XCircle size={16} />
                Unresolve
              </button>
            )}
            {issue.status !== "ignored" && (
              <button className="btn btn-ghost" onClick={() => updateStatus("ignored")}>
                <Eye size={16} />
                Ignore
              </button>
            )}
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="tabs">
        {["stacktrace", "events", "details"].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab === "stacktrace" ? "Stack Trace" : tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* ── Stack Trace Tab ── */}
      {activeTab === "stacktrace" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {exceptions.length === 0 ? (
            <div className="card">
              <p className="text-muted">
                {meta.message
                  ? `Message: ${meta.message}`
                  : "No stack trace available for this issue."}
              </p>
            </div>
          ) : (
            exceptions.map((exc, i) => (
              <div key={i} className="stacktrace">
                <div className="stacktrace-header">
                  <span className="stacktrace-type">{exc.type || "Error"}</span>
                  <span className="stacktrace-value">{exc.value || ""}</span>
                </div>
                {exc.stacktrace?.frames && exc.stacktrace.frames.length > 0 ? (
                  [...exc.stacktrace.frames].reverse().map((frame, fi) => (
                    <div key={fi} className="stacktrace-frame">
                      <span className="stacktrace-frame-file">
                        {frame.filename || frame.abs_path || frame.module || "unknown"}
                      </span>
                      {" in "}
                      <span className="stacktrace-frame-func">
                        {frame.function || "<anonymous>"}
                      </span>
                      {frame.lineno && (
                        <span className="stacktrace-frame-context">
                          {" at line "}
                          <span className="stacktrace-frame-line">{frame.lineno}</span>
                          {frame.colno && `:${frame.colno}`}
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="stacktrace-frame">
                    <span className="stacktrace-frame-context">No frames available</span>
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* ── Events Tab ── */}
      {activeTab === "events" && (
        <div>
          {events.length === 0 ? (
            <div className="card empty-state">
              <AlertTriangle size={48} className="empty-state-icon" />
              <h3>No events</h3>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Event ID</th>
                    <th>Timestamp</th>
                    <th>Received</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <span className="text-mono" style={{ fontSize: "0.8125rem" }}>
                          {event.event_id.substring(0, 12)}…
                        </span>
                      </td>
                      <td className="text-muted">{formatTime(event.timestamp)}</td>
                      <td className="text-muted">{formatRelativeTime(event.received_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Details Tab ── */}
      {activeTab === "details" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div className="card">
            <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>Issue Info</h3>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1.5rem", fontSize: "0.8125rem" }}>
              <span className="text-muted">ID</span>
              <span className="text-mono">{issue.id}</span>
              <span className="text-muted">Fingerprint</span>
              <span className="text-mono" style={{ wordBreak: "break-all" }}>{issue.fingerprint}</span>
              <span className="text-muted">First Seen</span>
              <span>{formatTime(issue.first_seen)}</span>
              <span className="text-muted">Last Seen</span>
              <span>{formatTime(issue.last_seen)}</span>
              <span className="text-muted">Total Events</span>
              <span className="text-mono">{issue.event_count}</span>
            </div>
          </div>

          {meta.tags && typeof meta.tags === "object" && Object.keys(meta.tags).length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>Tags</h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                {Object.entries(meta.tags as Record<string, string>).map(([k, v]) => (
                  <span key={k} className="badge badge-info">
                    {k}: {v}
                  </span>
                ))}
              </div>
            </div>
          )}

          {meta.sdk && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>SDK</h3>
              <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
                {(meta.sdk as { name?: string; version?: string }).name || "unknown"}{" "}
                {(meta.sdk as { version?: string }).version || ""}
              </p>
            </div>
          )}

          {/* Environment info */}
          {(meta.environment || meta.server_name || meta.logger || meta.release) && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>Environment</h3>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1.5rem", fontSize: "0.8125rem" }}>
                {meta.environment && (
                  <>
                    <span className="text-muted">Environment</span>
                    <span>{meta.environment as string}</span>
                  </>
                )}
                {meta.server_name && (
                  <>
                    <span className="text-muted">Server</span>
                    <span className="text-mono">{meta.server_name as string}</span>
                  </>
                )}
                {meta.logger && (
                  <>
                    <span className="text-muted">Logger</span>
                    <span className="text-mono">{meta.logger as string}</span>
                  </>
                )}
                {meta.release && (
                  <>
                    <span className="text-muted">Release</span>
                    <span className="text-mono">{meta.release as string}</span>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
