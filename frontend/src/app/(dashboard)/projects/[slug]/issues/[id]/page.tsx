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

  useEffect(() => {
    async function load() {
      try {
        const [issueData, eventsData] = await Promise.all([
          api.get<Issue>(`/api/v1/issues/${id}`),
          api.get<EventList>(`/api/v1/issues/${id}/events?limit=20`),
        ]);
        setIssue(issueData);
        setEvents(eventsData.items);
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
  function getExceptions(): ExceptionValue[] {
    if (events.length === 0) return [];
    const latestEvent = events[0];
    const data = latestEvent.data;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const exc = (data as any)?.exception;
    if (!exc?.values) return [];
    return exc.values as ExceptionValue[];
  }

  // Extract tags/context from latest event
  function getEventMeta() {
    if (events.length === 0) return {};
    const data = events[0].data;
    return {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      sdk: (data as any)?.sdk,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      contexts: (data as any)?.contexts,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      tags: (data as any)?.tags,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      message: (data as any)?.message,
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
          <h1 style={{ fontSize: "1.25rem", fontWeight: 600, marginBottom: "0.75rem", wordBreak: "break-word" }}>
            {issue.title}
          </h1>
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
        </div>
      )}
    </div>
  );
}
