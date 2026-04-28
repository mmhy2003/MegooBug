"use client";

import { Search, Bell, Menu } from "lucide-react";

interface HeaderProps {
  sidebarCollapsed: boolean;
  onMobileMenuOpen: () => void;
  userName?: string;
}

export function Header({
  sidebarCollapsed,
  onMobileMenuOpen,
  userName = "Admin",
}: HeaderProps) {
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

        {/* Search */}
        <div className="header-search">
          <Search size={16} className="header-search-icon" />
          <input
            type="text"
            className="header-search-input"
            placeholder="Search issues, projects..."
            id="global-search"
            aria-label="Global search"
          />
          <span className="header-search-shortcut">⌘K</span>
        </div>
      </div>

      <div className="header-actions">
        {/* Notifications */}
        <button className="notification-btn" aria-label="Notifications" id="notification-bell">
          <Bell size={20} />
          <span className="notification-badge">3</span>
        </button>

        {/* User avatar */}
        <div className="user-avatar" title={userName}>
          {userName.charAt(0).toUpperCase()}
        </div>
      </div>
    </header>
  );
}
