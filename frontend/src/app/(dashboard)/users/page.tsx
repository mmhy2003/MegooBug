import type { Metadata } from "next";
import { UserPlus } from "lucide-react";

export const metadata: Metadata = {
  title: "Users — MegooBug",
  description: "Manage users and roles for your bug tracking instance",
};

const users = [
  {
    id: 1,
    name: "Admin User",
    email: "admin@megoobug.local",
    role: "admin",
    status: "active",
    joined: "2026-01-15",
  },
  {
    id: 2,
    name: "Jane Developer",
    email: "jane@example.com",
    role: "developer",
    status: "active",
    joined: "2026-02-20",
  },
  {
    id: 3,
    name: "Bob Viewer",
    email: "bob@example.com",
    role: "viewer",
    status: "active",
    joined: "2026-03-10",
  },
  {
    id: 4,
    name: "Pending User",
    email: "pending@example.com",
    role: "developer",
    status: "invited",
    joined: "—",
  },
];

function getRoleBadge(role: string) {
  switch (role) {
    case "admin":
      return "badge badge-error";
    case "developer":
      return "badge badge-info";
    default:
      return "badge badge-warning";
  }
}

function getStatusBadge(status: string) {
  return status === "active" ? "badge badge-success" : "badge badge-warning";
}

export default function UsersPage() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Users</h1>
        <button className="btn btn-primary" id="invite-user-btn">
          <UserPlus size={16} />
          Invite User
        </button>
      </div>

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Joined</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <div className="user-avatar" style={{ width: 32, height: 32, fontSize: "0.75rem" }}>
                      {user.name.charAt(0)}
                    </div>
                    <span style={{ fontWeight: 500 }}>{user.name}</span>
                  </div>
                </td>
                <td className="text-muted">{user.email}</td>
                <td>
                  <span className={getRoleBadge(user.role)}>{user.role}</span>
                </td>
                <td>
                  <span className={getStatusBadge(user.status)}>{user.status}</span>
                </td>
                <td className="text-muted">{user.joined}</td>
                <td>
                  <button className="btn btn-ghost" style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}>
                    Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
