"use client";

import { useTheme } from "next-themes";
import { Sun, Moon, Monitor } from "lucide-react";
import { useEffect, useState } from "react";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  if (!mounted) return <div style={{ width: 36, height: 36 }} />;

  const options = [
    { value: "light", icon: Sun, label: "Light" },
    { value: "dark", icon: Moon, label: "Dark" },
    { value: "system", icon: Monitor, label: "System" },
  ] as const;

  return (
    <div
      style={{
        display: "flex",
        gap: "0.25rem",
        padding: "0.25rem",
        background: "var(--bg-input)",
        borderRadius: "var(--radius-sm)",
        border: "1px solid var(--border-color)",
      }}
    >
      {options.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          aria-label={`Switch to ${label} theme`}
          title={label}
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 32,
            height: 28,
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
            transition: "all 150ms ease",
            background:
              theme === value
                ? "rgba(var(--accent-primary-rgb), 0.15)"
                : "transparent",
            color:
              theme === value
                ? "var(--accent-primary)"
                : "var(--text-tertiary)",
          }}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}
