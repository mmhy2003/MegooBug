import type { Metadata } from "next";
import {
  AlertTriangle,
  FolderKanban,
  Activity,
  Users,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Dashboard — MegooBug",
  description: "Overview of your bug tracking metrics and recent issues",
};

// Placeholder data — will be replaced with API calls
const stats = [
  {
    label: "Total Projects",
    value: "12",
    icon: FolderKanban,
    accent: false,
  },
  {
    label: "Errors (24h)",
    value: "847",
    icon: AlertTriangle,
    accent: true,
  },
  {
    label: "Unresolved Issues",
    value: "156",
    icon: Activity,
    accent: true,
  },
  {
    label: "Active Users",
    value: "24",
    icon: Users,
    accent: false,
  },
];

const recentIssues = [
  {
    id: 1,
    title: "TypeError: Cannot read property 'map' of undefined",
    project: "web-frontend",
    level: "error",
    count: 42,
    lastSeen: "2 min ago",
  },
  {
    id: 2,
    title: "ConnectionRefusedError: Redis connection failed",
    project: "api-server",
    level: "fatal",
    count: 18,
    lastSeen: "5 min ago",
  },
  {
    id: 3,
    title: "Warning: Each child in a list should have a unique key",
    project: "web-frontend",
    level: "warning",
    count: 203,
    lastSeen: "12 min ago",
  },
  {
    id: 4,
    title: "PermissionError: Permission denied: '/tmp/cache'",
    project: "worker-service",
    level: "error",
    count: 7,
    lastSeen: "1 hour ago",
  },
  {
    id: 5,
    title: "TimeoutError: Request timed out after 30000ms",
    project: "api-server",
    level: "warning",
    count: 56,
    lastSeen: "2 hours ago",
  },
];

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

export default function DashboardPage() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {stats.map((stat) => {
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
              {recentIssues.map((issue) => (
                <tr key={issue.id} style={{ cursor: "pointer" }}>
                  <td>
                    <span className="text-mono" style={{ fontSize: "0.8125rem" }}>
                      {issue.title}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-info">{issue.project}</span>
                  </td>
                  <td>
                    <span className={getLevelBadgeClass(issue.level)}>
                      {issue.level}
                    </span>
                  </td>
                  <td>
                    <span className="text-mono">{issue.count}</span>
                  </td>
                  <td>
                    <span className="text-muted">{issue.lastSeen}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
