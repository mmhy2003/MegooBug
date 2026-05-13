"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  ChevronRight, Copy, Check, Loader2, Trash2,
  FolderKanban, AlertTriangle, UserPlus, Users, UsersRound,
} from "lucide-react";
import { api, ApiError, API_URL } from "@/lib/api";
import { useWS } from "@/components/websocket-provider";

interface Project {
  id: string;
  project_number: number;
  name: string;
  slug: string;
  platform: string | null;
  dsn_public_key: string;
  created_by: string;
  team_id: string | null;
  created_at: string;
  updated_at: string;
}

interface Issue {
  id: string;
  project_id: string;
  issue_number: number | null;
  title: string;
  fingerprint: string;
  status: string;
  level: string;
  first_seen: string;
  last_seen: string;
  event_count: number;
  metadata_: Record<string, unknown> | null;
}

interface IssueList {
  items: Issue[];
  total: number;
}

interface TrendPoint {
  date: string;
  count: number;
}

interface TrendData {
  project: string;
  days: number;
  data: TrendPoint[];
}

interface ProjectMember {
  user_id: string;
  user_name: string;
  user_email: string;
  user_role: string;
  notify_email: boolean;
  notify_inapp: boolean;
  joined_at: string;
}

interface UserItem {
  id: string;
  name: string;
  email: string;
  role: string;
}

export default function ProjectDetailPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const router = useRouter();
  const { lastMessage, subscribe, unsubscribe } = useWS();
  const searchParams = useSearchParams();

  const [project, setProject] = useState<Project | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [issueTotal, setIssueTotal] = useState(0);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const initialTab = searchParams.get("tab");
  const [activeTab, setActiveTab] = useState(
    initialTab && ["overview", "issues", "settings"].includes(initialTab)
      ? initialTab
      : "overview"
  );
  const [statusFilter, setStatusFilter] = useState("unresolved");
  const [envFilter, setEnvFilter] = useState("");
  const [environments, setEnvironments] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editName, setEditName] = useState("");
  const [editPlatform, setEditPlatform] = useState("");
  const [saving, setSaving] = useState(false);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [allUsers, setAllUsers] = useState<UserItem[]>([]);
  const [addingMember, setAddingMember] = useState<string | null>(null);
  const [removingMember, setRemovingMember] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<{ role: string } | null>(null);
  const [teams, setTeams] = useState<{ id: string; name: string; slug: string }[]>([]);
  const [editTeamId, setEditTeamId] = useState<string>("");

  // Subscribe to project-specific WebSocket channel
  useEffect(() => {
    if (!project) return;
    subscribe("project", project.id);
    return () => {
      unsubscribe("project", project.id);
    };
  }, [project, subscribe, unsubscribe]);

  // Real-time: handle new_event messages for this project
  useEffect(() => {
    if (!lastMessage || !project) return;
    if (lastMessage.type !== "new_event") return;
    if (lastMessage.project_id !== project.id) return;

    const iss = lastMessage.issue;
    if (!iss) return;

    if (lastMessage.is_new_issue) {
      // Prepend new issue
      setIssues((prev) => {
        const newIssue: Issue = {
          id: iss.id,
          project_id: project.id,
          issue_number: iss.issue_number || null,
          title: iss.title || "Unknown",
          fingerprint: "",
          status: iss.status || "unresolved",
          level: iss.level || "error",
          first_seen: iss.first_seen || new Date().toISOString(),
          last_seen: iss.last_seen || new Date().toISOString(),
          event_count: iss.event_count || 1,
          metadata_: null,
        };
        return [newIssue, ...prev];
      });
      setIssueTotal((prev) => prev + 1);
    } else {
      // Update existing issue's event_count and last_seen
      setIssues((prev) =>
        prev.map((i) =>
          i.id === iss.id
            ? {
                ...i,
                event_count: iss.event_count || i.event_count + 1,
                last_seen: iss.last_seen || new Date().toISOString(),
              }
            : i
        )
      );
    }
  }, [lastMessage, project]);

  useEffect(() => {
    async function load() {
      try {
        const proj = await api.get<Project>(`/api/v1/projects/${slug}`);
        setProject(proj);
        setEditName(proj.name);
        setEditPlatform(proj.platform || "");
        setEditTeamId(proj.team_id || "");

        // Load current user info for role check
        try {
          const me = await api.get<{ role: string }>("/api/v1/users/me");
          setCurrentUser(me);
        } catch {}

        // Trend fetch is non-critical — don't redirect if it fails
        try {
          const trendData = await api.get<TrendData>(
            `/api/v1/stats/projects/${slug}/trends?days=14`
          );
          setTrend(trendData.data);
        } catch {
          // Trend data unavailable — show empty chart
        }

        // Load available environments
        try {
          const envs = await api.get<string[]>(
            `/api/v1/projects/${slug}/environments`
          );
          setEnvironments(envs);
        } catch {
          // Environments unavailable — hide dropdown
        }
      } catch {
        router.push("/projects");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [slug, router]);

  useEffect(() => {
    if (!project) return;
    loadIssues();
  }, [project, statusFilter, envFilter]);

  async function loadIssues() {
    if (!project) return;
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (envFilter) params.set("environment", envFilter);
      params.set("limit", "50");
      const data = await api.get<IssueList>(
        `/api/v1/projects/${slug}/issues?${params.toString()}`
      );
      setIssues(data.items);
      setIssueTotal(data.total);
    } catch {
      // Ignore
    }
  }

  async function updateIssueStatus(issueId: string, status: string) {
    try {
      await api.patch(`/api/v1/issues/${issueId}`, { status });
      await loadIssues();
    } catch {
      // Ignore
    }
  }

  function getFullDSN() {
    if (!project) return "";
    const apiUrl = API_URL;
    try {
      const url = new URL(apiUrl);
      return `${url.protocol}//${project.dsn_public_key}@${url.host}/${project.project_number}`;
    } catch {
      return `${apiUrl}/api/${project.id}`;
    }
  }

  async function copyDSN() {
    try {
      await navigator.clipboard.writeText(getFullDSN());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {}
  }

  async function handleSaveSettings() {
    if (!project) return;
    setSaving(true);
    try {
      const updated = await api.patch<Project>(`/api/v1/projects/${slug}`, {
        name: editName,
        platform: editPlatform || null,
        team_id: editTeamId || null,
      });
      setProject(updated);
    } catch {}
    setSaving(false);
  }

  async function handleDelete() {
    if (!project) return;
    setDeleting(true);
    try {
      await api.delete(`/api/v1/projects/${slug}`);
      router.push("/projects");
    } catch {}
    setDeleting(false);
  }

  // Members management
  async function loadMembers() {
    if (!project) return;
    try {
      const data = await api.get<ProjectMember[]>(
        `/api/v1/projects/${slug}/members`
      );
      setMembers(data);
    } catch {}
  }

  async function loadUsers() {
    try {
      const data = await api.get<{ users: UserItem[] }>("/api/v1/users");
      setAllUsers(data.users || []);
    } catch {}
  }

  // Load members and teams when settings tab is active
  useEffect(() => {
    if (activeTab === "settings" && project) {
      loadMembers();
      if (currentUser?.role === "admin") {
        loadUsers();
        api.get<{ id: string; name: string; slug: string }[]>("/api/v1/teams")
          .then(setTeams)
          .catch(() => {});
      }
    }
  }, [activeTab, project]);

  const memberUserIds = new Set(members.map((m) => m.user_id));
  const availableUsers = allUsers.filter((u) => !memberUserIds.has(u.id));

  async function addMember(userId: string) {
    if (!project) return;
    setAddingMember(userId);
    try {
      await api.post(`/api/v1/projects/${slug}/members`, {
        user_id: userId,
        notify_email: true,
        notify_inapp: true,
      });
      await loadMembers();
    } catch {}
    setAddingMember(null);
  }

  async function removeMember(userId: string) {
    if (!project) return;
    setRemovingMember(userId);
    try {
      await api.delete(`/api/v1/projects/${slug}/members/${userId}`);
      await loadMembers();
    } catch {}
    setRemovingMember(null);
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

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
        <Loader2 size={32} className="spin" style={{ color: "var(--text-tertiary)" }} />
      </div>
    );
  }

  if (!project) return null;

  const maxTrend = Math.max(...trend.map((t) => t.count), 1);
  const apiUrl = API_URL;

  return (
    <div>
      {/* Breadcrumbs */}
      <div className="breadcrumbs">
        <Link href="/projects">Projects</Link>
        <ChevronRight size={14} className="separator" />
        <span style={{ color: "var(--text-primary)" }}>{project.name}</span>
      </div>

      {/* Header */}
      <div className="page-header">
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: "var(--radius-sm)",
              background: "rgba(var(--accent-primary-rgb), 0.1)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "var(--accent-primary)",
            }}
          >
            <FolderKanban size={24} />
          </div>
          <div>
            <h1 className="page-title" style={{ marginBottom: 0 }}>
              {project.name}
            </h1>
            <span className="text-muted" style={{ fontSize: "0.8125rem" }}>
              {project.platform || project.slug}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs">
        {["overview", "issues",
          ...((currentUser?.role === "admin" || currentUser?.role === "developer") ? ["settings"] : []),
        ].map((tab) => (
          <button
            key={tab}
            className={`tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {tab === "issues" && issueTotal > 0 && (
              <span style={{ marginLeft: "0.5rem", opacity: 0.7 }}>
                ({issueTotal})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Overview Tab ── */}
      {activeTab === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* DSN */}
          <div className="card">
            <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>
              Client DSN
            </h3>
            <p className="text-muted" style={{ fontSize: "0.8125rem", marginBottom: "0.75rem" }}>
              Use this DSN to configure Sentry SDKs to send events to this project.
            </p>
            <div className="dsn-display">
              <span className="dsn-value">
                {getFullDSN()}
              </span>
              <button
                className={`copy-btn ${copied ? "copied" : ""}`}
                onClick={copyDSN}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <div style={{ marginTop: "0.75rem" }}>
              <span className="text-muted" style={{ fontSize: "0.75rem" }}>
                Public Key: <code className="text-mono">{project.dsn_public_key}</code>
              </span>
            </div>
          </div>

          {/* Trend Chart */}
          <div className="card">
            <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>
              Error Trend (14 days)
            </h3>
            {trend.every((t) => t.count === 0) ? (
              <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
                No events received yet.
              </p>
            ) : (
              <div className="trend-chart">
                {trend.map((point) => (
                  <div
                    key={point.date}
                    className="trend-bar"
                    style={{
                      height: `${Math.max((point.count / maxTrend) * 100, 2)}%`,
                    }}
                  >
                    <div className="trend-bar-tooltip">
                      {point.date}: {point.count} events
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Project Info */}
          <div className="card">
            <h3 style={{ fontSize: "1rem", marginBottom: "0.75rem" }}>Details</h3>
            <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.5rem 1.5rem", fontSize: "0.8125rem" }}>
              <span className="text-muted">Slug</span>
              <span className="text-mono">{project.slug}</span>
              <span className="text-muted">Platform</span>
              <span>{project.platform || "—"}</span>
              <span className="text-muted">Created</span>
              <span>{new Date(project.created_at).toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      )}

      {/* ── Issues Tab ── */}
      {activeTab === "issues" && (
        <div>
          {/* Filters */}
          <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1rem", flexWrap: "wrap", alignItems: "center" }}>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {["unresolved", "resolved", "ignored", ""].map((s) => (
                <button
                  key={s}
                  className={`btn ${statusFilter === s ? "btn-primary" : "btn-ghost"}`}
                  style={{ padding: "0.375rem 0.75rem", fontSize: "0.8125rem" }}
                  onClick={() => setStatusFilter(s)}
                >
                  {s || "All"}
                </button>
              ))}
            </div>
            {environments.length > 0 && (
              <>
                <div style={{ width: 1, height: 24, background: "var(--border-primary)", margin: "0 0.25rem" }} />
                <select
                  id="env-filter"
                  className="input"
                  value={envFilter}
                  onChange={(e) => setEnvFilter(e.target.value)}
                  style={{
                    padding: "0.375rem 0.75rem",
                    fontSize: "0.8125rem",
                    minWidth: 140,
                    width: "auto",
                    background: envFilter ? "rgba(var(--accent-primary-rgb), 0.1)" : undefined,
                    borderColor: envFilter ? "var(--accent-primary)" : undefined,
                    color: envFilter ? "var(--accent-primary)" : undefined,
                  }}
                >
                  <option value="">All Environments</option>
                  {environments.map((env) => (
                    <option key={env} value={env}>{env}</option>
                  ))}
                </select>
              </>
            )}
          </div>

          {issues.length === 0 ? (
            <div className="card empty-state">
              <AlertTriangle size={48} className="empty-state-icon" />
              <h3 style={{ marginBottom: "0.5rem" }}>No issues found</h3>
              <p className="text-muted">
                {statusFilter
                  ? `No ${statusFilter} issues. Try a different filter.`
                  : "Send events via the Sentry SDK to start tracking issues."}
              </p>
            </div>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Level</th>
                    <th>Events</th>
                    <th>Env</th>
                    <th>Status</th>
                    <th>Last Seen</th>
                    {(currentUser?.role === "admin" || currentUser?.role === "developer") && <th>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {issues.map((issue) => (
                    <tr key={issue.id}>
                      <td style={{ maxWidth: 420 }}>
                        <Link
                          href={`/projects/${slug}/issues/${issue.id}`}
                          style={{ color: "var(--text-primary)", textDecoration: "none", display: "block" }}
                          title={issue.title}
                        >
                          {issue.issue_number && (
                            <span
                              className="text-mono"
                              style={{
                                fontSize: "0.6875rem",
                                color: "var(--accent-primary)",
                                fontWeight: 600,
                                marginBottom: "0.125rem",
                                display: "block",
                                letterSpacing: "0.025em",
                              }}
                            >
                              {slug.toUpperCase()}-{issue.issue_number}
                            </span>
                          )}
                          <span
                            className="text-mono"
                            style={{
                              fontSize: "0.8125rem",
                              display: "block",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {issue.title}
                          </span>
                        </Link>
                      </td>
                      <td>
                        <span className={getLevelBadgeClass(issue.level)}>
                          {issue.level}
                        </span>
                      </td>
                      <td>
                        <span className="text-mono">{issue.event_count}</span>
                      </td>
                      <td>
                        {issue.metadata_?.environment ? (
                          <span className="badge badge-info" style={{ fontSize: "0.6875rem" }}>
                            {issue.metadata_.environment as string}
                          </span>
                        ) : (
                          <span className="text-muted" style={{ fontSize: "0.75rem" }}>—</span>
                        )}
                      </td>
                      <td>
                        <span className="issue-meta-item">
                          <span className={`status-dot ${issue.status}`} />
                          {issue.status}
                        </span>
                      </td>
                      <td className="text-muted">
                        {formatRelativeTime(issue.last_seen)}
                      </td>
                      {(currentUser?.role === "admin" || currentUser?.role === "developer") && (
                        <td>
                          {issue.status === "unresolved" && (
                            <button
                              className="btn btn-ghost"
                              style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                              onClick={() => updateIssueStatus(issue.id, "resolved")}
                            >
                              Resolve
                            </button>
                          )}
                          {issue.status === "resolved" && (
                            <button
                              className="btn btn-ghost"
                              style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                              onClick={() => updateIssueStatus(issue.id, "unresolved")}
                            >
                              Unresolve
                            </button>
                          )}
                          {issue.status !== "ignored" && (
                            <button
                              className="btn btn-ghost"
                              style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                              onClick={() => updateIssueStatus(issue.id, "ignored")}
                            >
                              Ignore
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Settings Tab ── */}
      {activeTab === "settings" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div className="card">
            <h3 style={{ fontSize: "1rem", marginBottom: "1rem" }}>
              Project Settings
            </h3>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "1rem",
              }}
            >
              <div className="form-group">
                <label htmlFor="edit-name" className="label">Project Name</label>
                <input
                  id="edit-name"
                  className="input"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label htmlFor="edit-platform" className="label">Platform</label>
                <select
                  id="edit-platform"
                  className="input"
                  value={editPlatform}
                  onChange={(e) => setEditPlatform(e.target.value)}
                >
                  <option value="">None</option>
                  <option value="javascript">JavaScript</option>
                  <option value="typescript">TypeScript</option>
                  <option value="python">Python</option>
                  <option value="go">Go</option>
                  <option value="java">Java</option>
                  <option value="csharp">C#</option>
                  <option value="ruby">Ruby</option>
                  <option value="php">PHP</option>
                  <option value="rust">Rust</option>
                  <option value="react-native">React Native</option>
                  <option value="flutter">Flutter</option>
                  <option value="other">Other</option>
                </select>
              </div>
              {currentUser?.role === "admin" && (
                <div className="form-group">
                  <label htmlFor="edit-team" className="label" style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                    <UsersRound size={14} />
                    Assigned Team
                  </label>
                  <select
                    id="edit-team"
                    className="input"
                    value={editTeamId}
                    onChange={(e) => setEditTeamId(e.target.value)}
                  >
                    <option value="">No team</option>
                    {teams.map((t) => (
                      <option key={t.id} value={t.id}>{t.name}</option>
                    ))}
                  </select>
                  <span className="text-muted" style={{ fontSize: "0.7rem", marginTop: "0.25rem", display: "block" }}>
                    Team members automatically get access and notifications for this project.
                  </span>
                </div>
              )}
            </div>
            <div style={{ marginTop: "1rem" }}>
              <button
                className="btn btn-primary"
                onClick={handleSaveSettings}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>

          {/* Members Section */}
          <div className="card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ fontSize: "1rem", margin: 0, display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <Users size={18} />
                Members ({members.length})
              </h3>
            </div>

            {/* Current members list */}
            {members.length === 0 ? (
              <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
                No members assigned to this project.
              </p>
            ) : (
              <div className="member-list">
                {members.map((m) => (
                  <div key={m.user_id} className="member-item">
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 }}>
                      <div className="user-avatar" style={{ width: 32, height: 32, fontSize: "0.75rem" }}>
                        {m.user_name.charAt(0)}
                      </div>
                      <div>
                        <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                          {m.user_name}
                        </div>
                        <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                          {m.user_email} · <span className={m.user_role === "admin" ? "badge badge-error" : m.user_role === "developer" ? "badge badge-info" : "badge badge-warning"} style={{ fontSize: "0.625rem", padding: "0.1rem 0.4rem" }}>{m.user_role}</span>
                        </div>
                      </div>
                    </div>
                    {currentUser?.role === "admin" && (
                      <button
                        className="btn btn-ghost btn-danger-text"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => removeMember(m.user_id)}
                        disabled={removingMember === m.user_id}
                      >
                        {removingMember === m.user_id ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <Trash2 size={14} />
                        )}
                        Remove
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Add member (admin only) */}
            {currentUser?.role === "admin" && availableUsers.length > 0 && (
              <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
                <h4 style={{ fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.75rem", color: "var(--text-secondary)" }}>
                  Add Member
                </h4>
                <div className="member-list">
                  {availableUsers.map((u) => (
                    <div key={u.id} className="member-item">
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 }}>
                        <div className="user-avatar" style={{ width: 28, height: 28, fontSize: "0.7rem" }}>
                          {u.name.charAt(0)}
                        </div>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: "0.8125rem" }}>{u.name}</div>
                          <div className="text-muted" style={{ fontSize: "0.7rem" }}>{u.email}</div>
                        </div>
                      </div>
                      <button
                        className="btn btn-primary"
                        style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }}
                        onClick={() => addMember(u.id)}
                        disabled={addingMember === u.id}
                      >
                        {addingMember === u.id ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <UserPlus size={14} />
                        )}
                        Add
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Danger Zone — admin only */}
          {currentUser?.role === "admin" && (
            <div
              className="card"
              style={{ borderColor: "rgba(255, 51, 102, 0.3)" }}
            >
              <h3 style={{ fontSize: "1rem", marginBottom: "0.5rem", color: "var(--accent-error)" }}>
                Danger Zone
              </h3>
              <p className="text-muted" style={{ fontSize: "0.8125rem", marginBottom: "1rem" }}>
                Deleting a project will permanently remove all its issues and events.
              </p>
              <button
                className="btn btn-danger"
                onClick={() => setShowDeleteConfirm(true)}
              >
                <Trash2 size={16} />
                Delete Project
              </button>
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation */}
      {showDeleteConfirm && (
        <div className="confirm-overlay" onClick={() => setShowDeleteConfirm(false)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: "0.75rem" }}>Delete Project?</h3>
            <p className="text-muted" style={{ fontSize: "0.875rem", marginBottom: "1.5rem" }}>
              This will permanently delete <strong>{project.name}</strong> and all
              associated issues and events. This action cannot be undone.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button
                className="btn btn-ghost"
                onClick={() => setShowDeleteConfirm(false)}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={handleDelete}
                disabled={deleting}
              >
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
