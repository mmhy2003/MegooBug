"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FolderKanban, Plus, Loader2, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { CreateProjectModal } from "@/components/create-project-modal";
import { useWS } from "@/components/websocket-provider";

interface Project {
  id: string;
  project_number: number;
  name: string;
  slug: string;
  platform: string | null;
  dsn_public_key: string;
  created_at: string;
  unresolved_count: number;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const { lastMessage } = useWS();

  async function loadProjects() {
    try {
      const data = await api.get<Project[]>("/api/v1/projects");
      setProjects(data);
    } catch {
      // Ignore — show empty state
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadProjects();
  }, []);

  // Real-time: increment unresolved_count on project card when new issue arrives
  useEffect(() => {
    if (!lastMessage) return;
    if (lastMessage.type === "stats_update" && lastMessage.project_id && lastMessage.unresolved_delta > 0) {
      setProjects((prev) =>
        prev.map((p) =>
          p.id === lastMessage.project_id
            ? { ...p, unresolved_count: p.unresolved_count + lastMessage.unresolved_delta }
            : p
        )
      );
    }
  }, [lastMessage]);

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
        <h1 className="page-title">Projects</h1>
        <button
          className="btn btn-primary"
          id="create-project-btn"
          onClick={() => setShowCreate(true)}
        >
          <Plus size={16} />
          Create Project
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card empty-state">
          <FolderKanban size={48} className="empty-state-icon" />
          <h3 style={{ marginBottom: "0.5rem" }}>No projects yet</h3>
          <p className="text-muted" style={{ marginBottom: "1rem" }}>
            Create your first project to start tracking errors.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => setShowCreate(true)}
          >
            <Plus size={16} />
            Create Project
          </button>
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
            gap: "1rem",
          }}
        >
          {projects.map((project) => (
            <Link
              href={`/projects/${project.slug}`}
              key={project.id}
              style={{ textDecoration: "none", color: "inherit" }}
            >
              <div className="card" style={{ cursor: "pointer", position: "relative" }}>
                {project.unresolved_count > 0 && (
                  <div
                    style={{
                      position: "absolute",
                      top: "0.75rem",
                      right: "0.75rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      background: "rgba(239, 68, 68, 0.12)",
                      color: "#ef4444",
                      padding: "0.25rem 0.6rem",
                      borderRadius: "999px",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      lineHeight: 1,
                    }}
                  >
                    <AlertCircle size={13} />
                    {project.unresolved_count}
                  </div>
                )}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    marginBottom: "1rem",
                  }}
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
                    }}
                  >
                    <FolderKanban size={20} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>
                      {project.name}
                    </h3>
                    <span className="text-muted" style={{ fontSize: "0.75rem" }}>
                      {project.platform || project.slug}
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    fontSize: "0.8125rem",
                  }}
                >
                  <div>
                    <span className="text-muted">Slug: </span>
                    <span className="text-mono">{project.slug}</span>
                  </div>
                  <span className="text-muted">
                    {formatRelativeTime(project.created_at)}
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateProjectModal
          onClose={() => setShowCreate(false)}
          onCreated={(project) => {
            setProjects((prev) => [project, ...prev]);
          }}
        />
      )}
    </div>
  );
}
