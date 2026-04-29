"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, FolderKanban, AlertTriangle, X } from "lucide-react";
import { api } from "@/lib/api";

interface SearchResult {
  type: string;
  id: string;
  // Issue fields
  title?: string;
  status?: string;
  level?: string;
  project_id?: string;
  // Project fields
  name?: string;
  slug?: string;
  platform?: string;
}

interface SearchResponse {
  results: SearchResult[];
  query: string;
  error?: string;
}

interface Props {
  projectMap?: Map<string, { slug: string; name: string }>;
}

export function SearchPalette({ projectMap }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keyboard shortcut (Ctrl+K / Cmd+K)
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen(true);
      }
      if (e.key === "Escape") {
        setOpen(false);
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Auto-focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
      setResults([]);
      setSelectedIndex(0);
    }
  }, [open]);

  // Debounced search
  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const data = await api.get<SearchResponse>(
        `/api/v1/search?q=${encodeURIComponent(q)}`
      );
      setResults(data.results);
      setSelectedIndex(0);
    } catch {
      setResults([]);
    }
    setLoading(false);
  }, []);

  function handleChange(value: string) {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => doSearch(value), 200);
  }

  function navigateToResult(result: SearchResult) {
    setOpen(false);
    if (result.type === "projects") {
      router.push(`/projects/${result.slug}`);
    } else if (result.type === "issues") {
      // Find project slug from the project map or default
      const projSlug = projectMap?.get(result.project_id || "")?.slug || "_";
      router.push(`/projects/${projSlug}/issues/${result.id}`);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && results[selectedIndex]) {
      navigateToResult(results[selectedIndex]);
    }
  }

  if (!open) return null;

  return (
    <div className="modal-overlay" onClick={() => setOpen(false)}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 600,
          marginTop: "15vh",
          alignSelf: "flex-start",
        }}
      >
        <div
          style={{
            background: "var(--bg-card)",
            border: "1px solid var(--border-color)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-elevated)",
            overflow: "hidden",
          }}
        >
          {/* Search Input */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              padding: "1rem 1.25rem",
              borderBottom: "1px solid var(--border-color)",
            }}
          >
            <Search size={18} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
            <input
              ref={inputRef}
              type="text"
              placeholder="Search issues, projects..."
              value={query}
              onChange={(e) => handleChange(e.target.value)}
              onKeyDown={handleKeyDown}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                outline: "none",
                fontSize: "1rem",
                color: "var(--text-primary)",
                fontFamily: "var(--font-sans)",
              }}
            />
            <button className="modal-close" onClick={() => setOpen(false)} style={{ padding: "0.125rem" }}>
              <X size={16} />
            </button>
          </div>

          {/* Results */}
          <div style={{ maxHeight: 400, overflowY: "auto" }}>
            {loading && (
              <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>
                Searching...
              </div>
            )}

            {!loading && query && results.length === 0 && (
              <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>
                No results for &ldquo;{query}&rdquo;
              </div>
            )}

            {!loading && results.length > 0 && (
              <div style={{ padding: "0.5rem" }}>
                {results.map((result, i) => (
                  <div
                    key={`${result.type}-${result.id}`}
                    onClick={() => navigateToResult(result)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.75rem",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "var(--radius-sm)",
                      cursor: "pointer",
                      background: i === selectedIndex ? "rgba(var(--accent-primary-rgb), 0.1)" : "transparent",
                      transition: "background 100ms",
                    }}
                  >
                    <div style={{ color: result.type === "projects" ? "var(--accent-primary)" : "var(--accent-error)" }}>
                      {result.type === "projects" ? <FolderKanban size={16} /> : <AlertTriangle size={16} />}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          fontWeight: 500,
                          color: "var(--text-primary)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {result.title || result.name}
                      </div>
                      <div style={{ fontSize: "0.6875rem", color: "var(--text-tertiary)" }}>
                        {result.type === "projects" ? `Project · ${result.slug}` : `Issue · ${result.level}`}
                      </div>
                    </div>
                    {result.status && (
                      <span className={`status-dot ${result.status}`} />
                    )}
                  </div>
                ))}
              </div>
            )}

            {!query && (
              <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-tertiary)", fontSize: "0.8125rem" }}>
                Type to search issues and projects
              </div>
            )}
          </div>

          {/* Footer */}
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: "1.5rem",
              padding: "0.5rem 1rem",
              borderTop: "1px solid var(--border-color)",
              fontSize: "0.6875rem",
              color: "var(--text-tertiary)",
            }}
          >
            <span>↑↓ Navigate</span>
            <span>↵ Open</span>
            <span>esc Close</span>
          </div>
        </div>
      </div>
    </div>
  );
}
