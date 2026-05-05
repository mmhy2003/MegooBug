"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ChevronRight, Loader2, Clock, Hash, AlertTriangle,
  CheckCircle, XCircle, Eye, ChevronDown, ChevronUp,
  Globe, Monitor, User, Cpu, List, Package, Code,
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
  context_line?: string;
  pre_context?: string[];
  post_context?: string[];
  in_app?: boolean;
}

interface Breadcrumb {
  type?: string;
  category?: string;
  message?: string;
  level?: string;
  timestamp?: string;
  data?: Record<string, unknown>;
}

interface RequestData {
  url?: string;
  method?: string;
  headers?: Record<string, string>;
  query_string?: string;
  data?: unknown;
  env?: Record<string, string>;
}

interface UserContext {
  id?: string;
  email?: string;
  username?: string;
  ip_address?: string;
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
  const [expandedFrames, setExpandedFrames] = useState<Set<string>>(new Set());

  function toggleFrame(key: string) {
    setExpandedFrames((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

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
        router.push(`/projects/${slug}?tab=issues`);
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

    // Extract breadcrumbs
    let breadcrumbs: Breadcrumb[] = [];
    if (data?.breadcrumbs) {
      const bc = data.breadcrumbs;
      breadcrumbs = Array.isArray(bc) ? bc : (bc.values || []);
    }

    // Extract request
    const request: RequestData | null = data?.request || null;

    // Extract user
    const user: UserContext | null = data?.user || null;

    // Extract modules
    const modules: Record<string, string> | null = data?.modules || null;

    // Extract extra
    const extra: Record<string, unknown> | null = data?.extra || null;

    return {
      sdk: data?.sdk,
      contexts: data?.contexts,
      tags: data?.tags,
      message: displayMessage,
      logger: data?.logger,
      environment: data?.environment,
      server_name: data?.server_name,
      release: data?.release,
      breadcrumbs,
      request,
      user,
      modules,
      extra,
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
        <Link href={`/projects/${slug}?tab=issues`}>{slug}</Link>
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
        {(["stacktrace", "breadcrumbs", "context", "events", "details"] as const).map((tab) => {
          const labels: Record<string, string> = {
            stacktrace: "Stack Trace",
            breadcrumbs: "Breadcrumbs",
            context: "Context",
            events: "Events",
            details: "Details",
          };
          return (
            <button
              key={tab}
              className={`tab ${activeTab === tab ? "active" : ""}`}
              onClick={() => setActiveTab(tab)}
            >
              {labels[tab]}
            </button>
          );
        })}
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
                  [...exc.stacktrace.frames].reverse().map((frame, fi) => {
                    const frameKey = `${i}-${fi}`;
                    const isExpanded = expandedFrames.has(frameKey);
                    const hasContext = frame.context_line || (frame.pre_context && frame.pre_context.length > 0);
                    return (
                      <div key={fi}>
                        <div
                          className="stacktrace-frame"
                          style={{
                            cursor: hasContext ? "pointer" : "default",
                            borderLeft: frame.in_app ? "3px solid var(--accent-primary)" : "3px solid transparent",
                            paddingLeft: "0.75rem",
                          }}
                          onClick={() => hasContext && toggleFrame(frameKey)}
                        >
                          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem", flex: 1, minWidth: 0 }}>
                            {hasContext && (isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                            <span className="stacktrace-frame-file" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
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
                          </span>
                          {frame.in_app && <span className="badge badge-info" style={{ fontSize: "0.625rem", padding: "1px 6px" }}>app</span>}
                        </div>
                        {isExpanded && hasContext && (
                          <div style={{ background: "var(--bg-primary)", borderRadius: "var(--radius-sm)", margin: "0 0 0.25rem 1rem", overflow: "auto", fontSize: "0.75rem", fontFamily: "var(--font-mono)", lineHeight: 1.7, border: "1px solid var(--border-primary)" }}>
                            {frame.pre_context?.map((line, li) => (
                              <div key={`pre-${li}`} style={{ padding: "0 1rem", color: "var(--text-tertiary)", whiteSpace: "pre" }}>
                                <span style={{ display: "inline-block", width: 48, textAlign: "right", marginRight: 16, opacity: 0.5, userSelect: "none" }}>{(frame.lineno || 0) - (frame.pre_context!.length - li)}</span>
                                {line}
                              </div>
                            ))}
                            {frame.context_line && (
                              <div style={{ padding: "0 1rem", background: "rgba(255,51,102,0.08)", color: "var(--text-primary)", fontWeight: 600, whiteSpace: "pre", borderLeft: "3px solid var(--status-error)" }}>
                                <span style={{ display: "inline-block", width: 48, textAlign: "right", marginRight: 16, opacity: 0.7, userSelect: "none" }}>{frame.lineno}</span>
                                {frame.context_line}
                              </div>
                            )}
                            {frame.post_context?.map((line, li) => (
                              <div key={`post-${li}`} style={{ padding: "0 1rem", color: "var(--text-tertiary)", whiteSpace: "pre" }}>
                                <span style={{ display: "inline-block", width: 48, textAlign: "right", marginRight: 16, opacity: 0.5, userSelect: "none" }}>{(frame.lineno || 0) + li + 1}</span>
                                {line}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })
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

      {/* ── Breadcrumbs Tab ── */}
      {activeTab === "breadcrumbs" && (
        <div className="card">
          {meta.breadcrumbs && (meta.breadcrumbs as Breadcrumb[]).length > 0 ? (
            <div style={{ maxHeight: 600, overflow: "auto" }}>
              <table style={{ width: "100%", fontSize: "0.8125rem" }}>
                <thead>
                  <tr>
                    <th style={{ width: 60 }}>Type</th>
                    <th style={{ width: 120 }}>Category</th>
                    <th>Message</th>
                    <th style={{ width: 50 }}>Level</th>
                    <th style={{ width: 160 }}>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {(meta.breadcrumbs as Breadcrumb[]).map((bc, i) => (
                    <tr key={i}>
                      <td><span className="text-mono" style={{ fontSize: "0.75rem" }}>{bc.type || "—"}</span></td>
                      <td><span className="badge badge-info" style={{ fontSize: "0.625rem" }}>{bc.category || "default"}</span></td>
                      <td style={{ wordBreak: "break-word", maxWidth: 400 }}>
                        <span style={{ color: "var(--text-primary)" }}>{bc.message || "—"}</span>
                        {bc.data && Object.keys(bc.data).length > 0 && (
                          <div style={{ marginTop: 4 }}>
                            {Object.entries(bc.data).slice(0, 5).map(([k, v]) => (
                              <span key={k} style={{ display: "inline-block", marginRight: 8, fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                                <span style={{ color: "var(--text-muted)" }}>{k}:</span> {String(v).substring(0, 80)}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td>
                        {bc.level && (
                          <span className={`badge ${bc.level === "error" || bc.level === "fatal" ? "badge-error" : bc.level === "warning" ? "badge-warning" : "badge-info"}`} style={{ fontSize: "0.625rem" }}>
                            {bc.level}
                          </span>
                        )}
                      </td>
                      <td className="text-muted" style={{ fontSize: "0.75rem", whiteSpace: "nowrap" }}>
                        {bc.timestamp ? new Date(bc.timestamp).toLocaleTimeString() : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-muted">No breadcrumbs available for this event.</p>
          )}
        </div>
      )}

      {/* ── Context Tab ── */}
      {activeTab === "context" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* HTTP Request */}
          {meta.request && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Globe size={16} /> HTTP Request
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1.5rem", fontSize: "0.8125rem" }}>
                {(meta.request as RequestData).method && (
                  <>
                    <span className="text-muted">Method</span>
                    <span className="badge badge-info" style={{ justifySelf: "start" }}>{(meta.request as RequestData).method}</span>
                  </>
                )}
                {(meta.request as RequestData).url && (
                  <>
                    <span className="text-muted">URL</span>
                    <span className="text-mono" style={{ wordBreak: "break-all" }}>{(meta.request as RequestData).url}</span>
                  </>
                )}
                {(meta.request as RequestData).query_string && (
                  <>
                    <span className="text-muted">Query</span>
                    <span className="text-mono" style={{ wordBreak: "break-all" }}>{(meta.request as RequestData).query_string}</span>
                  </>
                )}
              </div>
              {(meta.request as RequestData).headers && Object.keys((meta.request as RequestData).headers!).length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <h4 style={{ fontSize: "0.8125rem", marginBottom: "0.5rem", color: "var(--text-secondary)" }}>Headers</h4>
                  <div style={{ background: "var(--bg-primary)", borderRadius: "var(--radius-sm)", padding: "0.75rem 1rem", fontSize: "0.75rem", fontFamily: "var(--font-mono)", maxHeight: 200, overflow: "auto", border: "1px solid var(--border-primary)" }}>
                    {Object.entries((meta.request as RequestData).headers!).map(([k, v]) => (
                      <div key={k} style={{ marginBottom: 2 }}>
                        <span style={{ color: "var(--accent-primary)" }}>{k}</span>: <span style={{ color: "var(--text-secondary)" }}>{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* User Context */}
          {meta.user && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <User size={16} /> User
              </h3>
              <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1.5rem", fontSize: "0.8125rem" }}>
                {(meta.user as UserContext).id && (<><span className="text-muted">ID</span><span className="text-mono">{(meta.user as UserContext).id}</span></>)}
                {(meta.user as UserContext).email && (<><span className="text-muted">Email</span><span>{(meta.user as UserContext).email}</span></>)}
                {(meta.user as UserContext).username && (<><span className="text-muted">Username</span><span>{(meta.user as UserContext).username}</span></>)}
                {(meta.user as UserContext).ip_address && (<><span className="text-muted">IP Address</span><span className="text-mono">{(meta.user as UserContext).ip_address}</span></>)}
              </div>
            </div>
          )}

          {/* Device / OS / Browser / Runtime */}
          {meta.contexts && typeof meta.contexts === "object" && (() => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const ctx = meta.contexts as any;
            const sections = [
              { key: "browser", icon: <Globe size={16} />, label: "Browser" },
              { key: "os", icon: <Monitor size={16} />, label: "Operating System" },
              { key: "device", icon: <Cpu size={16} />, label: "Device" },
              { key: "runtime", icon: <Code size={16} />, label: "Runtime" },
            ];
            const rendered = sections.filter((s) => ctx[s.key] && Object.keys(ctx[s.key]).length > 0);
            if (rendered.length === 0) return null;
            return (
              <div className="card">
                <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Monitor size={16} /> Device &amp; Runtime
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "1rem" }}>
                  {rendered.map((s) => (
                    <div key={s.key} style={{ background: "var(--bg-primary)", borderRadius: "var(--radius-sm)", padding: "0.75rem 1rem", border: "1px solid var(--border-primary)" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "0.5rem", display: "flex", alignItems: "center", gap: "0.4rem" }}>{s.icon} {s.label}</div>
                      {Object.entries(ctx[s.key]).filter(([k]) => k !== "type").map(([k, v]) => (
                        <div key={k} style={{ fontSize: "0.8125rem", marginBottom: 2 }}>
                          <span className="text-muted">{k}: </span>
                          <span style={{ color: "var(--text-primary)" }}>{String(v).substring(0, 120)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Extra Data */}
          {meta.extra && typeof meta.extra === "object" && Object.keys(meta.extra as Record<string, unknown>).length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <List size={16} /> Extra Data
              </h3>
              <div style={{ background: "var(--bg-primary)", borderRadius: "var(--radius-sm)", padding: "0.75rem 1rem", fontSize: "0.75rem", fontFamily: "var(--font-mono)", maxHeight: 300, overflow: "auto", border: "1px solid var(--border-primary)" }}>
                {Object.entries(meta.extra as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} style={{ marginBottom: 4 }}>
                    <span style={{ color: "var(--accent-primary)" }}>{k}</span>: <span style={{ color: "var(--text-secondary)", wordBreak: "break-all" }}>{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Modules */}
          {meta.modules && typeof meta.modules === "object" && Object.keys(meta.modules as Record<string, string>).length > 0 && (
            <div className="card">
              <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Package size={16} /> Modules ({Object.keys(meta.modules as Record<string, string>).length})
              </h3>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", maxHeight: 200, overflow: "auto" }}>
                {Object.entries(meta.modules as Record<string, string>).map(([name, ver]) => (
                  <span key={name} className="badge badge-info" style={{ fontSize: "0.6875rem" }}>
                    {name} {ver}
                  </span>
                ))}
              </div>
            </div>
          )}

          {!meta.request && !meta.user && !(meta.contexts && typeof meta.contexts === "object") && !meta.extra && !meta.modules && (
            <div className="card">
              <p className="text-muted">No additional context available for this event.</p>
            </div>
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
