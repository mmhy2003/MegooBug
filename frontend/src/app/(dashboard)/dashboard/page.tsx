"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  FolderKanban,
  Activity,
  Users,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";

interface DashboardStats {
  total_projects: number;
  errors_24h: number;
  unresolved_issues: number;
  active_users: number;
}

interface RecentIssue {
  id: string;
  project_id: string;
  title: string;
  status: string;
  level: string;
  event_count: number;
  first_seen: string;
  last_seen: string;
}

interface IssueList {
  items: RecentIssue[];
  total: number;
}

interface Project {
  id: string;
  slug: string;
  name: string;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [issues, setIssues] = useState<RecentIssue[]>([]);
  const [projects, setProjects] = useState<Map<string, Project>>(new Map());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [statsData, projectsData] = await Promise.allSettled([
          api.get<DashboardStats>("/api/v1/stats/dashboard"),
          api.get<Project[]>("/api/v1/projects"),
        ]);

        if (statsData.status === "fulfilled") {
          setStats(statsData.value);
        }

        if (projectsData.status === "fulfilled") {
          const projMap = new Map<string, Project>();
          projectsData.value.forEach((p) => projMap.set(p.id, p));
          setProjects(projMap);

          // Load recent issues from first project, or all
          if (projectsData.value.length > 0) {
            try {
              // Get issues across all projects by trying each
              const allIssues: RecentIssue[] = [];
              for (const proj of projectsData.value.slice(0, 5)) {
                try {
                  const issData = await api.get<IssueList>(
                    `/api/v1/projects/${proj.slug}/issues?limit=10&status=unresolved`
                  );
                  allIssues.push(...issData.items);
                } catch {
                  // Project might have no issues
                }
              }
              // Sort by last_seen and take top 10
              allIssues.sort(
                (a, b) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime()
              );
              setIssues(allIssues.slice(0, 10));
            } catch {
              // Ignore
            }
          }
        }
      } catch {
        // Ignore — show empty state
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function formatRelativeTime(isoString: string) {
    if (!isoString) return "—";
    const diff = Date.now() - new Date(isoString).getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "just now";
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  function getLevelBadgeClass(level: string) {
    switch (level) {
      case "fatal":
        return "badge badge-error badge-pulse";
      case "error":
        return "badge badge-error";
      case "warning":
        return "badge badge-warning";
      default:
        return "badge badge-info";
    }
  }

  function getProjectSlug(projectId: string): string {
    const p = projects.get(projectId);
    return p?.slug || "";
  }

  function getProjectName(projectId: string): string {
    const p = projects.get(projectId);
    return p?.name || p?.slug || "—";
  }

  const statCards = [
    {
      label: "Total Projects",
      value: stats?.total_projects ?? 0,
      icon: FolderKanban,
      accent: false,
      href: "/projects",
    },
    {
      label: "Errors (24h)",
      value: stats?.errors_24h ?? 0,
      icon: AlertTriangle,
      accent: true,
      href: null,
    },
    {
      label: "Unresolved Issues",
      value: stats?.unresolved_issues ?? 0,
      icon: Activity,
      accent: true,
      href: null,
    },
    {
      label: "Active Users",
      value: stats?.active_users ?? 0,
      icon: Users,
      accent: false,
      href: "/users",
    },
  ];

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
        <Loader2 size={32} className="spin" style={{ color: "var(--text-tertiary)" }} />
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {statCards.map((stat) => {
          const Icon = stat.icon;
          const cardContent = (
            <div className="stat-card" key={stat.label}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div className="stat-card-label">{stat.label}</div>
                  <div
                    className={`stat-card-value ${stat.accent ? "accent" : ""}`}
                  >
                    {stat.value}
                  </div>
                </div>
                <div
                  style={{
                    color: stat.accent
                      ? "var(--accent-primary)"
                      : "var(--text-tertiary)",
                    opacity: 0.5,
                  }}
                >
                  <Icon size={32} />
                </div>
              </div>
            </div>
          );

          if (stat.href) {
            return (
              <Link
                key={stat.label}
                href={stat.href}
                style={{ textDecoration: "none", color: "inherit" }}
              >
                {cardContent}
              </Link>
            );
          }
          return <div key={stat.label}>{cardContent}</div>;
        })}
      </div>

      {/* Recent Issues */}
      <div style={{ marginTop: "1.5rem" }}>
        <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>
          Recent Unresolved Issues
        </h2>
        {issues.length === 0 ? (
          <div className="card empty-state">
            <AlertTriangle size={48} className="empty-state-icon" />
            <h3 style={{ marginBottom: "0.5rem" }}>No issues yet</h3>
            <p className="text-muted">Connect a Sentry SDK to start tracking errors.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Project</th>
                  <th>Level</th>
                  <th>Events</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue) => (
                  <tr key={issue.id} style={{ cursor: "pointer" }}>
                    <td>
                      <Link
                        href={`/projects/${getProjectSlug(issue.project_id)}/issues/${issue.id}`}
                        style={{ color: "var(--text-primary)", textDecoration: "none" }}
                      >
                        <span className="text-mono" style={{ fontSize: "0.8125rem" }}>
                          {issue.title}
                        </span>
                      </Link>
                    </td>
                    <td>
                      <Link
                        href={`/projects/${getProjectSlug(issue.project_id)}`}
                        style={{ textDecoration: "none" }}
                      >
                        <span className="badge badge-info">
                          {getProjectName(issue.project_id)}
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
                      <span className="text-muted">
                        {formatRelativeTime(issue.last_seen)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
