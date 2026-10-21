"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Search, Menu } from "lucide-react";
import { NotificationBell } from "@/components/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";
interface HeaderProps {
  sidebarCollapsed: boolean;
  onMobileMenuOpen: () => void;
  onSearchOpen?: () => void;
  userName?: string;
}

export function Header({
  sidebarCollapsed,
  onMobileMenuOpen,
  onSearchOpen,
  userName = "Admin",
}: HeaderProps) {
  const pathname = usePathname();
  const onProfile = pathname.startsWith("/profile");

  return (
    <header
      className={`header ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
      id="main-header"
    >
      <div style={{ display: "flex", alignItems: "center", gap: "1rem", flex: 1 }}>
        {/* Mobile menu button */}
        <button className="mobile-menu-btn" onClick={onMobileMenuOpen} aria-label="Open menu">
          <Menu size={22} />
        </button>

        {/* Search trigger */}
        <div
          className="header-search"
          onClick={onSearchOpen}
          style={{ cursor: "pointer" }}
        >
          <Search size={16} className="header-search-icon" />
          <input
            type="text"
            className="header-search-input"
            placeholder="Search issues, projects..."
            id="global-search"
            aria-label="Global search"
            readOnly
            onFocus={onSearchOpen}
            style={{ cursor: "pointer" }}
          />
          <span className="header-search-shortcut">⌘K</span>
        </div>
      </div>

      <div className="header-actions">
        {/* Theme switcher */}
        <ThemeToggle />

        {/* Notifications */}
        <NotificationBell />

        {/* User avatar → profile */}
        <Link
          href="/profile"
          className={`user-avatar ${onProfile ? "active" : ""}`}
          aria-label="Your profile"
          title="Your profile"
          aria-current={onProfile ? "page" : undefined}
        >
          {userName.charAt(0).toUpperCase()}
        </Link>
      </div>
    </header>
  );
}
