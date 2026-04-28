"use client";

import { useEffect, useState } from "react";
import { FolderKanban, Plus, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface Project {
  id: string;
  name: string;
  slug: string;
  platform: string | null;
  dsn_public_key: string;
  created_at: string;
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const data = await api.get<Project[]>("/api/v1/projects");
        setProjects(data);
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
        <button className="btn btn-primary" id="create-project-btn">
          <Plus size={16} />
          Create Project
        </button>
      </div>

      {projects.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: "3rem" }}>
          <FolderKanban size={48} style={{ color: "var(--text-tertiary)", marginBottom: "1rem" }} />
          <h3 style={{ marginBottom: "0.5rem" }}>No projects yet</h3>
          <p className="text-muted">Create your first project to start tracking errors.</p>
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
            <div className="card" key={project.id} style={{ cursor: "pointer" }}>
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
                  <span
                    className="text-muted"
                    style={{ fontSize: "0.75rem" }}
                  >
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
          ))}
        </div>
      )}
    </div>
  );
}
