"use client";

import { useEffect, useState } from "react";
import {
  Users,
  Plus,
  Loader2,
  Trash2,
  UserPlus,
  FolderKanban,
  Pencil,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import { api } from "@/lib/api";

interface Team {
  id: string;
  team_number: number;
  name: string;
  slug: string;
  created_at: string;
  member_count: number;
  project_count: number;
}

interface TeamMember {
  user_id: string;
  user_name: string;
  user_email: string;
  user_role: string;
  team_role: string;
  joined_at: string;
}

interface UserItem {
  id: string;
  name: string;
  email: string;
  role: string;
}

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newTeamName, setNewTeamName] = useState("");
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);
  const [teamMembers, setTeamMembers] = useState<Record<string, TeamMember[]>>({});
  const [loadingMembers, setLoadingMembers] = useState<string | null>(null);
  const [allUsers, setAllUsers] = useState<UserItem[]>([]);
  const [addingMember, setAddingMember] = useState<string | null>(null);
  const [removingMember, setRemovingMember] = useState<string | null>(null);
  const [deletingTeam, setDeletingTeam] = useState<string | null>(null);
  const [editingTeam, setEditingTeam] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);
  const [deleteConfirmTeam, setDeleteConfirmTeam] = useState<Team | null>(null);
  const [userRole, setUserRole] = useState("");

  useEffect(() => {
    loadTeams();
    api.get<{ role: string }>("/api/v1/users/me")
      .then((me) => setUserRole(me.role))
      .catch(() => {});
    api.get<{ users: UserItem[] }>("/api/v1/users")
      .then((data) => setAllUsers(data.users || []))
      .catch(() => {});
  }, []);

  async function loadTeams() {
    setLoading(true);
    try {
      const data = await api.get<Team[]>("/api/v1/teams");
      setTeams(data);
    } catch {}
    setLoading(false);
  }

  async function createTeam() {
    if (!newTeamName.trim()) return;
    setCreating(true);
    try {
      const team = await api.post<Team>("/api/v1/teams", { name: newTeamName.trim() });
      setTeams((prev) => [...prev, team]);
      setNewTeamName("");
      setShowCreateForm(false);
    } catch {}
    setCreating(false);
  }

  async function toggleExpand(slug: string) {
    if (expandedTeam === slug) {
      setExpandedTeam(null);
      return;
    }
    setExpandedTeam(slug);
    if (!teamMembers[slug]) {
      setLoadingMembers(slug);
      try {
        const members = await api.get<TeamMember[]>(`/api/v1/teams/${slug}/members`);
        setTeamMembers((prev) => ({ ...prev, [slug]: members }));
      } catch {}
      setLoadingMembers(null);
    }
  }

  async function addMemberToTeam(slug: string, userId: string) {
    setAddingMember(userId);
    try {
      await api.post(`/api/v1/teams/${slug}/members`, { user_id: userId, role: "member" });
      // Reload members
      const members = await api.get<TeamMember[]>(`/api/v1/teams/${slug}/members`);
      setTeamMembers((prev) => ({ ...prev, [slug]: members }));
      // Update team count
      setTeams((prev) => prev.map((t) => t.slug === slug ? { ...t, member_count: members.length } : t));
    } catch {}
    setAddingMember(null);
  }

  async function removeMemberFromTeam(slug: string, userId: string) {
    setRemovingMember(userId);
    try {
      await api.delete(`/api/v1/teams/${slug}/members/${userId}`);
      const members = await api.get<TeamMember[]>(`/api/v1/teams/${slug}/members`);
      setTeamMembers((prev) => ({ ...prev, [slug]: members }));
      setTeams((prev) => prev.map((t) => t.slug === slug ? { ...t, member_count: members.length } : t));
    } catch {}
    setRemovingMember(null);
  }

  async function deleteTeam(slug: string) {
    setDeletingTeam(slug);
    try {
      await api.delete(`/api/v1/teams/${slug}`);
      setTeams((prev) => prev.filter((t) => t.slug !== slug));
      if (expandedTeam === slug) setExpandedTeam(null);
    } catch {}
    setDeletingTeam(null);
  }

  async function saveTeamEdit(slug: string) {
    if (!editName.trim()) return;
    setSavingEdit(true);
    try {
      const updated = await api.patch<Team>(`/api/v1/teams/${slug}`, { name: editName.trim() });
      setTeams((prev) => prev.map((t) => t.slug === slug ? updated : t));
      // If expanded team slug changed, update
      if (expandedTeam === slug && updated.slug !== slug) {
        setExpandedTeam(updated.slug);
        setTeamMembers((prev) => {
          const members = prev[slug];
          const next = { ...prev };
          delete next[slug];
          if (members) next[updated.slug] = members;
          return next;
        });
      }
      setEditingTeam(null);
    } catch {}
    setSavingEdit(false);
  }

  function getMemberIds(slug: string): Set<string> {
    return new Set((teamMembers[slug] || []).map((m) => m.user_id));
  }

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
        <Loader2 size={32} className="spin" style={{ color: "var(--text-tertiary)" }} />
      </div>
    );
  }

  const isAdmin = userRole === "admin";

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Teams</h1>
        {isAdmin && (
          <button
            className="btn btn-primary"
            id="create-team-btn"
            onClick={() => setShowCreateForm(true)}
          >
            <Plus size={16} />
            Create Team
          </button>
        )}
      </div>

      {/* Create Team Form */}
      {showCreateForm && (
        <div
          className="card"
          style={{
            marginBottom: "1.5rem",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            padding: "1rem 1.25rem",
          }}
        >
          <Users size={20} style={{ color: "var(--accent-primary)", flexShrink: 0 }} />
          <input
            className="input"
            placeholder="Team name..."
            value={newTeamName}
            onChange={(e) => setNewTeamName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createTeam()}
            autoFocus
            style={{ flex: 1 }}
            id="new-team-name"
          />
          <button
            className="btn btn-primary"
            onClick={createTeam}
            disabled={creating || !newTeamName.trim()}
            style={{ padding: "0.5rem 1rem" }}
          >
            {creating ? <Loader2 size={16} className="spin" /> : <Check size={16} />}
            Create
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => { setShowCreateForm(false); setNewTeamName(""); }}
            style={{ padding: "0.5rem" }}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {teams.length === 0 ? (
        <div className="card empty-state">
          <Users size={48} className="empty-state-icon" />
          <h3 style={{ marginBottom: "0.5rem" }}>No teams yet</h3>
          <p className="text-muted" style={{ marginBottom: "1rem" }}>
            Create teams to organize users and manage project access.
          </p>
          {isAdmin && (
            <button
              className="btn btn-primary"
              onClick={() => setShowCreateForm(true)}
            >
              <Plus size={16} />
              Create Team
            </button>
          )}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {teams.map((team) => {
            const isExpanded = expandedTeam === team.slug;
            const members = teamMembers[team.slug] || [];
            const memberIds = getMemberIds(team.slug);
            const availableUsers = allUsers.filter((u) => !memberIds.has(u.id));
            const isEditing = editingTeam === team.slug;

            return (
              <div key={team.id} className="card" style={{ padding: 0, overflow: "hidden" }}>
                {/* Team Header Row */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    padding: "1rem 1.25rem",
                    cursor: "pointer",
                  }}
                  onClick={() => toggleExpand(team.slug)}
                >
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(var(--accent-primary-rgb), 0.1)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--accent-primary)",
                      flexShrink: 0,
                    }}
                  >
                    <Users size={20} />
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    {isEditing ? (
                      <div
                        style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          className="input"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && saveTeamEdit(team.slug)}
                          autoFocus
                          style={{ padding: "0.25rem 0.5rem", fontSize: "0.875rem" }}
                        />
                        <button
                          className="btn btn-primary"
                          style={{ padding: "0.25rem 0.5rem" }}
                          onClick={() => saveTeamEdit(team.slug)}
                          disabled={savingEdit}
                        >
                          {savingEdit ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
                        </button>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: "0.25rem 0.5rem" }}
                          onClick={() => setEditingTeam(null)}
                        >
                          <X size={14} />
                        </button>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontWeight: 600, fontSize: "0.9375rem" }}>{team.name}</div>
                        <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                          <span className="text-mono">{team.slug}</span>
                        </div>
                      </>
                    )}
                  </div>

                  {/* Stats badges */}
                  <div
                    style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexShrink: 0 }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.3rem",
                        fontSize: "0.8125rem",
                        color: "var(--text-secondary)",
                      }}
                      title="Members"
                    >
                      <Users size={14} />
                      {team.member_count}
                    </span>
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.3rem",
                        fontSize: "0.8125rem",
                        color: "var(--text-secondary)",
                      }}
                      title="Projects"
                    >
                      <FolderKanban size={14} />
                      {team.project_count}
                    </span>

                    {isAdmin && (
                      <>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: "0.35rem", fontSize: "0.75rem" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setEditingTeam(team.slug);
                            setEditName(team.name);
                          }}
                          title="Rename team"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          className="btn btn-ghost btn-danger-text"
                          style={{ padding: "0.35rem", fontSize: "0.75rem" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteConfirmTeam(team);
                          }}
                          disabled={deletingTeam === team.slug}
                          title="Delete team"
                        >
                          {deletingTeam === team.slug ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <Trash2 size={14} />
                          )}
                        </button>
                      </>
                    )}
                  </div>

                  <span style={{ color: "var(--text-tertiary)", flexShrink: 0 }}>
                    {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </span>
                </div>

                {/* Expanded Section — Members */}
                {isExpanded && (
                  <div
                    style={{
                      borderTop: "1px solid var(--border-color)",
                      padding: "1rem 1.25rem",
                    }}
                  >
                    {loadingMembers === team.slug ? (
                      <div style={{ display: "flex", justifyContent: "center", padding: "1rem" }}>
                        <Loader2 size={20} className="spin" style={{ color: "var(--text-tertiary)" }} />
                      </div>
                    ) : (
                      <>
                        {/* Current Members */}
                        <h4
                          style={{
                            fontSize: "0.8125rem",
                            fontWeight: 600,
                            color: "var(--text-secondary)",
                            marginBottom: "0.75rem",
                          }}
                        >
                          Members ({members.length})
                        </h4>

                        {members.length === 0 ? (
                          <p className="text-muted" style={{ fontSize: "0.8125rem" }}>
                            No members in this team yet.
                          </p>
                        ) : (
                          <div className="member-list">
                            {members.map((m) => (
                              <div key={m.user_id} className="member-item">
                                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 }}>
                                  <div
                                    className="user-avatar"
                                    style={{ width: 32, height: 32, fontSize: "0.75rem" }}
                                  >
                                    {m.user_name.charAt(0)}
                                  </div>
                                  <div>
                                    <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                                      {m.user_name}
                                    </div>
                                    <div className="text-muted" style={{ fontSize: "0.75rem" }}>
                                      {m.user_email} ·{" "}
                                      <span
                                        className={
                                          m.team_role === "admin"
                                            ? "badge badge-error"
                                            : "badge badge-info"
                                        }
                                        style={{ fontSize: "0.625rem", padding: "0.1rem 0.4rem" }}
                                      >
                                        {m.team_role}
                                      </span>
                                    </div>
                                  </div>
                                </div>
                                {isAdmin && (
                                  <button
                                    className="btn btn-ghost btn-danger-text"
                                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                    onClick={() => removeMemberFromTeam(team.slug, m.user_id)}
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

                        {/* Add Members (admin only) */}
                        {isAdmin && availableUsers.length > 0 && (
                          <div
                            style={{
                              marginTop: "1rem",
                              borderTop: "1px solid var(--border-color)",
                              paddingTop: "1rem",
                            }}
                          >
                            <h4
                              style={{
                                fontSize: "0.8125rem",
                                fontWeight: 600,
                                color: "var(--text-secondary)",
                                marginBottom: "0.75rem",
                              }}
                            >
                              Add Member
                            </h4>
                            <div className="member-list">
                              {availableUsers.map((u) => (
                                <div key={u.id} className="member-item">
                                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1 }}>
                                    <div
                                      className="user-avatar"
                                      style={{ width: 28, height: 28, fontSize: "0.7rem" }}
                                    >
                                      {u.name.charAt(0)}
                                    </div>
                                    <div>
                                      <div style={{ fontWeight: 500, fontSize: "0.8125rem" }}>
                                        {u.name}
                                      </div>
                                      <div className="text-muted" style={{ fontSize: "0.7rem" }}>
                                        {u.email}
                                      </div>
                                    </div>
                                  </div>
                                  <button
                                    className="btn btn-primary"
                                    style={{ padding: "0.25rem 0.625rem", fontSize: "0.75rem" }}
                                    onClick={() => addMemberToTeam(team.slug, u.id)}
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
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Delete Team Confirmation Modal */}
      {deleteConfirmTeam && (
        <div className="confirm-overlay" onClick={() => setDeleteConfirmTeam(null)}>
          <div className="confirm-dialog" onClick={(e) => e.stopPropagation()}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: "var(--radius-full, 50%)",
                background: "rgba(255, 51, 102, 0.1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 1rem",
              }}
            >
              <AlertTriangle size={24} style={{ color: "var(--accent-error)" }} />
            </div>
            <h3 style={{ marginBottom: "0.5rem", textAlign: "center" }}>Delete Team</h3>
            <p
              className="text-muted"
              style={{ fontSize: "0.875rem", marginBottom: "0.5rem", textAlign: "center" }}
            >
              Are you sure you want to delete <strong>{deleteConfirmTeam.name}</strong>?
            </p>
            <p
              className="text-muted"
              style={{ fontSize: "0.8125rem", marginBottom: "1.5rem", textAlign: "center", opacity: 0.8 }}
            >
              {deleteConfirmTeam.project_count > 0
                ? `${deleteConfirmTeam.project_count} project${deleteConfirmTeam.project_count > 1 ? "s" : ""} will be unassigned from this team.`
                : "No projects are currently assigned to this team."}
              {" "}Members will be removed from the team. This action cannot be undone.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
              <button
                className="btn btn-ghost"
                onClick={() => setDeleteConfirmTeam(null)}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                onClick={() => {
                  deleteTeam(deleteConfirmTeam.slug);
                  setDeleteConfirmTeam(null);
                }}
                disabled={deletingTeam === deleteConfirmTeam.slug}
              >
                {deletingTeam === deleteConfirmTeam.slug ? (
                  <><Loader2 size={16} className="spin" /> Deleting...</>
                ) : (
                  <><Trash2 size={16} /> Delete Team</>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
