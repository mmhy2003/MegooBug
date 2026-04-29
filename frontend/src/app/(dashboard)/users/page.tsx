"use client";

import { useEffect, useState } from "react";
import {
  UserPlus,
  Loader2,
  Users as UsersIcon,
  FolderKanban,
  Mail,
  Trash2,
  RotateCw,
  Copy,
  Check,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
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

interface InviteItem {
  id: string;
  email: string;
  role: string;
  token: string;
  expires_at: string;
  created_at: string;
}

interface UserListResponse {
  users: UserItem[];
  total: number;
}

interface InviteListResponse {
  invites: InviteItem[];
  total: number;
}

export default function UsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [invites, setInvites] = useState<InviteItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [manageUser, setManageUser] = useState<UserItem | null>(null);
  const [resendingId, setResendingId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [copiedInviteId, setCopiedInviteId] = useState<string | null>(null);

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    setLoading(true);
    try {
      const [userData, inviteData] = await Promise.all([
        api.get<UserListResponse>("/api/v1/users"),
        api.get<InviteListResponse>("/api/v1/invites"),
      ]);
      setUsers(userData.users);
      setInvites(inviteData.invites);
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

  async function resendInvite(invite: InviteItem) {
    setResendingId(invite.id);
    try {
      const newInvite = await api.post<InviteItem>("/api/v1/invites", {
        email: invite.email,
        role: invite.role,
      });
      // Replace old invite in list
      setInvites((prev) =>
        prev.map((i) => (i.id === invite.id ? newInvite : i))
      );
    } catch {}
    setResendingId(null);
  }

  async function revokeInvite(inviteId: string) {
    setRevokingId(inviteId);
    try {
      await api.delete(`/api/v1/invites/${inviteId}`);
      setInvites((prev) => prev.filter((i) => i.id !== inviteId));
    } catch {}
    setRevokingId(null);
  }

  function getInviteLink(token: string) {
    const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
    return `${baseUrl}/register?token=${token}`;
  }

  async function copyInviteLink(invite: InviteItem) {
    try {
      await navigator.clipboard.writeText(getInviteLink(invite.token));
      setCopiedInviteId(invite.id);
      setTimeout(() => setCopiedInviteId(null), 2000);
    } catch {}
  }

  function isExpired(expiresAt: string) {
    return new Date(expiresAt) < new Date();
  }

  function formatDate(isoString: string) {
    if (!isoString) return "—";
    return new Date(isoString).toLocaleDateString();
  }

  function formatRelativeTime(isoString: string) {
    if (!isoString) return "";
    const diff = new Date(isoString).getTime() - Date.now();
    if (diff <= 0) return "Expired";
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours < 1) return "< 1h left";
    if (hours < 24) return `${hours}h left`;
    const days = Math.floor(hours / 24);
    return `${days}d left`;
  }

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
        <Loader2 size={32} className="spin" style={{ color: "var(--text-tertiary)" }} />
      </div>
    );
  }

  // Filter out expired invites for display (only show pending)
  const pendingInvites = invites.filter((i) => !isExpired(i.expires_at));
  const expiredInvites = invites.filter((i) => isExpired(i.expires_at));

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

      {users.length === 0 && pendingInvites.length === 0 ? (
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
              {/* Active / Registered users */}
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

              {/* Pending Invites */}
              {pendingInvites.map((invite) => (
                <tr key={`invite-${invite.id}`} style={{ opacity: 0.85 }}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <div
                        className="user-avatar"
                        style={{
                          width: 32,
                          height: 32,
                          fontSize: "0.75rem",
                          background: "rgba(var(--accent-primary-rgb), 0.15)",
                          color: "var(--accent-primary)",
                          border: "1px dashed rgba(var(--accent-primary-rgb), 0.4)",
                        }}
                      >
                        <Mail size={14} />
                      </div>
                      <span
                        style={{
                          fontWeight: 500,
                          fontStyle: "italic",
                          color: "var(--text-secondary)",
                        }}
                      >
                        Pending invite
                      </span>
                    </div>
                  </td>
                  <td className="text-muted">{invite.email}</td>
                  <td>
                    <span
                      className={
                        invite.role === "developer"
                          ? "badge badge-info"
                          : "badge badge-warning"
                      }
                    >
                      {invite.role}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-invited">
                      <Mail size={10} />
                      invited
                    </span>
                  </td>
                  <td className="text-muted" style={{ fontSize: "0.8125rem" }}>
                    <span title={`Expires: ${new Date(invite.expires_at).toLocaleString()}`}>
                      {formatRelativeTime(invite.expires_at)}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => copyInviteLink(invite)}
                        title="Copy invite link"
                      >
                        {copiedInviteId === invite.id ? (
                          <Check size={13} />
                        ) : (
                          <Copy size={13} />
                        )}
                        {copiedInviteId === invite.id ? "Copied" : "Link"}
                      </button>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => resendInvite(invite)}
                        disabled={resendingId === invite.id}
                        title="Resend invite (generates new token)"
                      >
                        {resendingId === invite.id ? (
                          <Loader2 size={13} className="spin" />
                        ) : (
                          <RotateCw size={13} />
                        )}
                        Resend
                      </button>
                      <button
                        className="btn btn-ghost btn-danger-text"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => revokeInvite(invite.id)}
                        disabled={revokingId === invite.id}
                        title="Revoke invite"
                      >
                        {revokingId === invite.id ? (
                          <Loader2 size={13} className="spin" />
                        ) : (
                          <Trash2 size={13} />
                        )}
                        Revoke
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

              {/* Expired Invites (dimmed, optional) */}
              {expiredInvites.map((invite) => (
                <tr key={`expired-${invite.id}`} style={{ opacity: 0.45 }}>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <div
                        className="user-avatar"
                        style={{
                          width: 32,
                          height: 32,
                          fontSize: "0.75rem",
                          background: "rgba(var(--accent-error-rgb, 255,51,102), 0.1)",
                          color: "var(--accent-error)",
                          border: "1px dashed rgba(var(--accent-error-rgb, 255,51,102), 0.3)",
                        }}
                      >
                        <Mail size={14} />
                      </div>
                      <span
                        style={{
                          fontWeight: 500,
                          fontStyle: "italic",
                          color: "var(--text-tertiary)",
                        }}
                      >
                        Expired invite
                      </span>
                    </div>
                  </td>
                  <td className="text-muted">{invite.email}</td>
                  <td>
                    <span className="badge" style={{ opacity: 0.6 }}>
                      {invite.role}
                    </span>
                  </td>
                  <td>
                    <span className="badge badge-expired">
                      expired
                    </span>
                  </td>
                  <td className="text-muted" style={{ fontSize: "0.8125rem" }}>
                    {formatDate(invite.created_at)}
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "0.375rem" }}>
                      <button
                        className="btn btn-ghost"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => resendInvite(invite)}
                        disabled={resendingId === invite.id}
                        title="Resend invite (generates new token)"
                      >
                        {resendingId === invite.id ? (
                          <Loader2 size={13} className="spin" />
                        ) : (
                          <RotateCw size={13} />
                        )}
                        Re-invite
                      </button>
                      <button
                        className="btn btn-ghost btn-danger-text"
                        style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                        onClick={() => revokeInvite(invite.id)}
                        disabled={revokingId === invite.id}
                        title="Delete expired invite"
                      >
                        {revokingId === invite.id ? (
                          <Loader2 size={13} className="spin" />
                        ) : (
                          <Trash2 size={13} />
                        )}
                        Delete
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
          onCreated={() => loadAll()}
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
