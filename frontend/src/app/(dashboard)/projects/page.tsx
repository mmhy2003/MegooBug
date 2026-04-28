import type { Metadata } from "next";
import { FolderKanban, Plus } from "lucide-react";

export const metadata: Metadata = {
  title: "Projects — MegooBug",
  description: "Manage your tracked projects and view error statistics",
};

const projects = [
  {
    id: 1,
    name: "Web Frontend",
    slug: "web-frontend",
    platform: "JavaScript",
    errorCount: 342,
    lastEvent: "2 min ago",
  },
  {
    id: 2,
    name: "API Server",
    slug: "api-server",
    platform: "Python",
    errorCount: 128,
    lastEvent: "5 min ago",
  },
  {
    id: 3,
    name: "Worker Service",
    slug: "worker-service",
    platform: "Python",
    errorCount: 45,
    lastEvent: "1 hour ago",
  },
  {
    id: 4,
    name: "Mobile App",
    slug: "mobile-app",
    platform: "React Native",
    errorCount: 89,
    lastEvent: "30 min ago",
  },
];

export default function ProjectsPage() {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Projects</h1>
        <button className="btn btn-primary" id="create-project-btn">
          <Plus size={16} />
          Create Project
        </button>
      </div>

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
                  {project.platform}
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
                <span className="text-muted">Errors: </span>
                <span className="text-mono text-accent">
                  {project.errorCount}
                </span>
              </div>
              <span className="text-muted">{project.lastEvent}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
