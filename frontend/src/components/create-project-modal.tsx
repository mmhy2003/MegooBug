"use client";

import { useState, FormEvent } from "react";
import { X, Copy, Check } from "lucide-react";
import { api, ApiError } from "@/lib/api";

interface Project {
  id: string;
  name: string;
  slug: string;
  platform: string | null;
  dsn_public_key: string;
  created_at: string;
}

interface Props {
  onClose: () => void;
  onCreated: (project: Project) => void;
}

const PLATFORMS = [
  { value: "", label: "Select platform (optional)" },
  { value: "javascript", label: "JavaScript" },
  { value: "typescript", label: "TypeScript" },
  { value: "python", label: "Python" },
  { value: "go", label: "Go" },
  { value: "java", label: "Java" },
  { value: "csharp", label: "C#" },
  { value: "ruby", label: "Ruby" },
  { value: "php", label: "PHP" },
  { value: "rust", label: "Rust" },
  { value: "react-native", label: "React Native" },
  { value: "flutter", label: "Flutter" },
  { value: "other", label: "Other" },
];

export function CreateProjectModal({ onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [platform, setPlatform] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<Project | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const project = await api.post<Project>("/api/v1/projects", {
        name,
        platform: platform || null,
      });
      setCreated(project);
      onCreated(project);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to create project");
      }
    } finally {
      setLoading(false);
    }
  }

  function getDSN() {
    if (!created) return "";
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // Parse the host from the API URL to build the Sentry DSN format:
    // <protocol>://<public_key>@<host>/api/<project_id>
    try {
      const url = new URL(apiUrl);
      return `${url.protocol}//${created.dsn_public_key}@${url.host}/api/${created.id}`;
    } catch {
      return `${apiUrl}/api/${created.id}`;
    }
  }

  async function copyDSN() {
    try {
      await navigator.clipboard.writeText(getDSN());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{created ? "Project Created" : "Create Project"}</h2>
          <button className="modal-close" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {created ? (
          <div>
            <p style={{ color: "var(--text-secondary)", marginBottom: "1rem" }}>
              Your project <strong>{created.name}</strong> has been created successfully.
              Use the DSN below to configure your Sentry SDK:
            </p>

            <label className="label">Client DSN</label>
            <div className="dsn-display">
              <span className="dsn-value">{getDSN()}</span>
              <button
                className={`copy-btn ${copied ? "copied" : ""}`}
                onClick={copyDSN}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy"}
              </button>
            </div>

            <p className="text-muted" style={{ marginTop: "0.75rem", fontSize: "0.8125rem" }}>
              Paste this into your Sentry SDK&apos;s <code>dsn</code> option — e.g.{" "}
              <code>Sentry.init({"{"} dsn: &quot;...&quot; {"}"})</code>
            </p>

            <div className="modal-actions">
              <button className="btn btn-primary" onClick={onClose}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit}>
            {error && <div className="auth-error" style={{ marginBottom: "1rem" }}>{error}</div>}

            <div className="form-group" style={{ marginBottom: "1rem" }}>
              <label htmlFor="project-name" className="label">
                Project Name
              </label>
              <input
                id="project-name"
                className="input"
                placeholder="My Awesome App"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label htmlFor="project-platform" className="label">
                Platform
              </label>
              <select
                id="project-platform"
                className="input"
                value={platform}
                onChange={(e) => setPlatform(e.target.value)}
              >
                {PLATFORMS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="modal-actions">
              <button type="button" className="btn btn-ghost" onClick={onClose}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading || !name.trim()}
              >
                {loading ? "Creating..." : "Create Project"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
