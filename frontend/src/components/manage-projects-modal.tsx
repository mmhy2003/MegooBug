"use client";

import { useState, useEffect } from "react";
import { X, Plus, Trash2, Loader2, FolderKanban } from "lucide-react";
import { api } from "@/lib/api";

interface Project {
  id: string;
  name: string;
  slug: string;
  platform: string | null;
}

interface Membership {
  project_id: string;
  project_name: string;
  project_slug: string;
  notify_email: boolean;
  notify_inapp: boolean;
}

interface ManageProjectsModalProps {
  userId: string;
  userName: string;
  onClose: () => void;
}

export function ManageProjectsModal({
  userId,
  userName,
  onClose,
}: ManageProjectsModalProps) {
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState<string | null>(null);
  const [removing, setRemoving] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      // Load all projects (admin sees all)
      const projects = await api.get<Project[]>("/api/v1/projects");
      setAllProjects(projects);

      // Load memberships for each project
      const membershipList: Membership[] = [];
      for (const project of projects) {
        try {
          const members = await api.get<
            { user_id: string; notify_email: boolean; notify_inapp: boolean }[]
          >(`/api/v1/projects/${project.slug}/members`);
          const match = members.find((m) => m.user_id === userId);
          if (match) {
            membershipList.push({
              project_id: project.id,
              project_name: project.name,
              project_slug: project.slug,
              notify_email: match.notify_email,
              notify_inapp: match.notify_inapp,
            });
          }
        } catch {
          // Skip projects that fail to load members
        }
      }
      setMemberships(membershipList);
    } catch {
      // Ignore
    } finally {
      setLoading(false);
    }
  }

  const assignedIds = new Set(memberships.map((m) => m.project_id));
  const availableProjects = allProjects.filter((p) => !assignedIds.has(p.id));

  async function addToProject(project: Project) {
    setAdding(project.id);
    try {
      await api.post(`/api/v1/projects/${project.slug}/members`, {
        user_id: userId,
        notify_email: true,
        notify_inapp: true,
      });
      setMemberships((prev) => [
        ...prev,
        {
          project_id: project.id,
          project_name: project.name,
          project_slug: project.slug,
          notify_email: true,
          notify_inapp: true,
        },
      ]);
    } catch {
      // Ignore
    }
    setAdding(null);
  }

  async function removeFromProject(membership: Membership) {
    setRemoving(membership.project_id);
    try {
      await api.delete(
        `/api/v1/projects/${membership.project_slug}/members/${userId}`
      );
      setMemberships((prev) =>
        prev.filter((m) => m.project_id !== membership.project_id)
      );
    } catch {
      // Ignore
    }
    setRemoving(null);
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal manage-projects-modal"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>Manage Projects — {userName}</h2>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              padding: "3rem",
            }}
          >
            <Loader2
              size={28}
              className="spin"
              style={{ color: "var(--text-tertiary)" }}
            />
          </div>
        ) : (
          <div className="modal-body" style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Assigned Projects */}
            <div>
              <h3
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  marginBottom: "0.75rem",
                  color: "var(--text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Assigned Projects ({memberships.length})
              </h3>
              {memberships.length === 0 ? (
                <p
                  className="text-muted"
                  style={{ fontSize: "0.8125rem", padding: "0.5rem 0" }}
                >
                  No projects assigned yet.
                </p>
              ) : (
                <div className="member-list">
                  {memberships.map((m) => (
                    <div key={m.project_id} className="member-item">
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.75rem",
                          flex: 1,
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(var(--accent-primary-rgb), 0.1)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "var(--accent-primary)",
                            flexShrink: 0,
                          }}
                        >
                          <FolderKanban size={16} />
                        </div>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                            {m.project_name}
                          </div>
                          <div
                            className="text-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            {m.project_slug}
                          </div>
                        </div>
                      </div>
                      <button
                        className="btn btn-ghost btn-danger-text"
                        style={{
                          padding: "0.25rem 0.5rem",
                          fontSize: "0.75rem",
                        }}
                        onClick={() => removeFromProject(m)}
                        disabled={removing === m.project_id}
                      >
                        {removing === m.project_id ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <Trash2 size={14} />
                        )}
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Available Projects */}
            <div>
              <h3
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  marginBottom: "0.75rem",
                  color: "var(--text-secondary)",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                }}
              >
                Available Projects ({availableProjects.length})
              </h3>
              {availableProjects.length === 0 ? (
                <p
                  className="text-muted"
                  style={{ fontSize: "0.8125rem", padding: "0.5rem 0" }}
                >
                  All projects are already assigned.
                </p>
              ) : (
                <div className="member-list">
                  {availableProjects.map((p) => (
                    <div key={p.id} className="member-item">
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.75rem",
                          flex: 1,
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: "var(--radius-sm)",
                            background: "rgba(var(--accent-primary-rgb), 0.08)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            color: "var(--text-tertiary)",
                            flexShrink: 0,
                          }}
                        >
                          <FolderKanban size={16} />
                        </div>
                        <div>
                          <div style={{ fontWeight: 500, fontSize: "0.875rem" }}>
                            {p.name}
                          </div>
                          <div
                            className="text-muted"
                            style={{ fontSize: "0.75rem" }}
                          >
                            {p.slug}
                          </div>
                        </div>
                      </div>
                      <button
                        className="btn btn-primary"
                        style={{
                          padding: "0.25rem 0.625rem",
                          fontSize: "0.75rem",
                        }}
                        onClick={() => addToProject(p)}
                        disabled={adding === p.id}
                      >
                        {adding === p.id ? (
                          <Loader2 size={14} className="spin" />
                        ) : (
                          <Plus size={14} />
                        )}
                        Assign
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
