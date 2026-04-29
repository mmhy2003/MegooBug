"use client";

import { useEffect, useState } from "react";
import { UserPlus, Loader2, Users as UsersIcon, FolderKanban } from "lucide-react";
import { api } from "@/lib/api";
import { InviteUserModal } from "@/components/invite-user-modal";
import { ManageProjectsModal } from "@/components/manage-projects-modal";

interface UserItem {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

interface UserListResponse {
  users: UserItem[];
  total: number;
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [manageUser, setManageUser] = useState<UserItem | null>(null);

  useEffect(() => {
    loadUsers();
  }, []);

  async function loadUsers() {
    try {
      const data = await api.get<UserListResponse>("/api/v1/users");
      setUsers(data.users);
    } catch {
      // Might fail for non-admin users
    } finally {
      setLoading(false);
    }
  }

  async function toggleUserStatus(userId: string) {
    setUpdatingId(userId);
    try {
      const updated = await api.patch<UserItem>(`/api/v1/users/${userId}/status`);
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch {}
    setUpdatingId(null);
  }

  async function changeUserRole(userId: string, role: string) {
    setUpdatingId(userId);
    try {
      const updated = await api.patch<UserItem>(`/api/v1/users/${userId}/role`, { role });
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)));
    } catch {}
    setUpdatingId(null);
  }

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

  function formatDate(isoString: string) {
    if (!isoString) return "—";
    return new Date(isoString).toLocaleDateString();
  }

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
        <h1 className="page-title">Users</h1>
        <button
          className="btn btn-primary"
          id="invite-user-btn"
          onClick={() => setShowInvite(true)}
        >
          <UserPlus size={16} />
          Invite User
        </button>
      </div>

      {users.length === 0 ? (
        <div className="card empty-state">
          <UsersIcon size={48} className="empty-state-icon" />
          <h3 style={{ marginBottom: "0.5rem" }}>No users found</h3>
          <p className="text-muted">Invite team members to start collaborating.</p>
        </div>
      ) : (
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
                    <select
                      className="input"
                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", width: "auto" }}
                      value={user.role}
                      onChange={(e) => changeUserRole(user.id, e.target.value)}
                      disabled={updatingId === user.id}
                    >
                      <option value="admin">admin</option>
                      <option value="developer">developer</option>
                      <option value="viewer">viewer</option>
                    </select>
                  </td>
                  <td>
                    <span className={user.is_active ? "badge badge-success" : "badge badge-warning"}>
                      {user.is_active ? "active" : "disabled"}
                    </span>
                  </td>
                  <td className="text-muted">{formatDate(user.created_at)}</td>
                  <td>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => setManageUser(user)}
                      >
                        <FolderKanban size={13} />
                        Projects
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => toggleUserStatus(user.id)}
                        disabled={updatingId === user.id}
                      >
                        {user.is_active ? "Disable" : "Enable"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showInvite && (
        <InviteUserModal
          onClose={() => setShowInvite(false)}
          onCreated={() => loadUsers()}
        />
      )}

      {manageUser && (
        <ManageProjectsModal
          userId={manageUser.id}
          userName={manageUser.name}
          onClose={() => setManageUser(null)}
        />
      )}
    </div>
  );
}
