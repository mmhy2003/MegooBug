"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  FolderKanban,
  Users,
  Settings,
  Bug,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Loader2,
} from "lucide-react";
import { api } from "@/lib/api";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
  adminOnly?: boolean;
}

const navItems: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { label: "Projects", href: "/projects", icon: FolderKanban },
  { label: "Users", href: "/users", icon: Users, adminOnly: true },
  { label: "Settings", href: "/settings", icon: Settings },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
  userRole?: string;
  userName?: string;
}

export function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onMobileClose,
  userRole = "admin",
  userName = "Admin",
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);

  const sidebarClasses = [
    "sidebar",
    collapsed ? "collapsed" : "",
    mobileOpen ? "mobile-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const visibleItems = navItems.filter(
    (item) => !item.adminOnly || userRole === "admin"
  );

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await api.post("/api/v1/auth/logout");
    } catch {
      // Even if the API call fails, redirect to login
    }
    router.push("/login");
  }

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={`sidebar-overlay ${mobileOpen ? "visible" : ""}`}
        onClick={onMobileClose}
      />

      <aside className={sidebarClasses} id="main-sidebar">
        {/* Header */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <Bug size={20} />
          </div>
          <span className="sidebar-brand">MegooBug</span>
        </div>

        {/* Navigation */}
        <nav className="sidebar-nav" aria-label="Main navigation">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href || pathname.startsWith(item.href + "/");

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`nav-item ${isActive ? "active" : ""}`}
                title={collapsed ? item.label : undefined}
                onClick={onMobileClose}
              >
                <span className="nav-icon">
                  <Icon size={20} />
                </span>
                <span className="nav-label">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="sidebar-footer">
          {/* User info */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              padding: "0.5rem 0.25rem",
            }}
          >
            <div className="user-avatar">
              {userName.charAt(0).toUpperCase()}
            </div>
            {!collapsed && (
              <div
                style={{
                  flex: 1,
                  minWidth: 0,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {userName}
                </div>
                <div
                  style={{
                    fontSize: "0.6875rem",
                    color: "var(--text-tertiary)",
                    textTransform: "capitalize",
                  }}
                >
                  {userRole}
                </div>
              </div>
            )}
            {!collapsed && (
              <button
                style={{
                  padding: "0.375rem",
                  background: "none",
                  border: "none",
                  color: loggingOut ? "var(--accent-primary)" : "var(--text-tertiary)",
                  cursor: loggingOut ? "wait" : "pointer",
                  display: "flex",
                  alignItems: "center",
                }}
                title="Logout"
                onClick={handleLogout}
                disabled={loggingOut}
              >
                {loggingOut ? (
                  <Loader2 size={16} className="spin" />
                ) : (
                  <LogOut size={16} />
                )}
              </button>
            )}
          </div>

          {/* Collapse toggle */}
          <button
            className="sidebar-toggle"
            onClick={onToggle}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? (
              <ChevronRight size={16} />
            ) : (
              <ChevronLeft size={16} />
            )}
          </button>
        </div>
      </aside>
    </>
  );
}
