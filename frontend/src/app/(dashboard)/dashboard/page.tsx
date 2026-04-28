"use client";

import { useEffect, useState } from "react";
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
  title: string;
  project_id: string;
  level: string;
  event_count: number;
  last_seen: string;
  status: string;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [issues, setIssues] = useState<RecentIssue[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [statsData, issuesData] = await Promise.allSettled([
          api.get<DashboardStats>("/api/v1/stats/dashboard"),
          api.get<{ items: RecentIssue[] }>("/api/v1/projects/_/issues"),
        ]);

        if (statsData.status === "fulfilled") {
          setStats(statsData.value);
        }
        // Issues endpoint might fail if no projects exist yet — that's fine
        if (issuesData.status === "fulfilled") {
          setIssues(issuesData.value.items || []);
        }
      } catch {
        // Ignore — we show empty state
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
    if (minutes < 60) return `${minutes} min ago`;
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

  const statCards = [
    {
      label: "Total Projects",
      value: stats?.total_projects ?? 0,
      icon: FolderKanban,
      accent: false,
    },
    {
      label: "Errors (24h)",
      value: stats?.errors_24h ?? 0,
      icon: AlertTriangle,
      accent: true,
    },
    {
      label: "Unresolved Issues",
      value: stats?.unresolved_issues ?? 0,
      icon: Activity,
      accent: true,
    },
    {
      label: "Active Users",
      value: stats?.active_users ?? 0,
      icon: Users,
      accent: false,
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
          return (
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
        })}
      </div>

      {/* Recent Issues */}
      <div style={{ marginTop: "1.5rem" }}>
        <h2 style={{ fontSize: "1.125rem", marginBottom: "1rem" }}>
          Recent Issues
        </h2>
        {issues.length === 0 ? (
          <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
            <p className="text-muted">No issues yet. Connect a Sentry SDK to start tracking errors.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Issue</th>
                  <th>Level</th>
                  <th>Events</th>
                  <th>Last Seen</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue) => (
                  <tr key={issue.id} style={{ cursor: "pointer" }}>
                    <td>
                      <span className="text-mono" style={{ fontSize: "0.8125rem" }}>
                        {issue.title}
                      </span>
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
