"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { Sidebar } from "@/components/sidebar";
import { Header } from "@/components/header";
import { SearchPalette } from "@/components/search-palette";
import { WebSocketProvider } from "@/components/websocket-provider";
import { api } from "@/lib/api";

interface CurrentUser {
  id: string;
  name: string;
  email: string;
  role: string;
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    async function loadUser() {
      try {
        const userData = await api.get<CurrentUser>("/api/v1/users/me");
        setUser(userData);
      } catch {
        router.push("/login");
        return;
      } finally {
        setLoading(false);
      }
    }
    loadUser();
  }, [router]);

  // Close mobile menu on resize
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 767) {
        setMobileOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "100vh",
          background: "var(--bg-primary)",
        }}
      >
        <Loader2
          size={36}
          className="spin"
          style={{ color: "var(--accent-primary)" }}
        />
      </div>
    );
  }

  if (!user) return null;

  return (
    <WebSocketProvider>
      <div className="app-layout scanlines">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
          userRole={user.role}
          userName={user.name}
        />

        <div
          className={`app-main ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}
        >
          <Header
            sidebarCollapsed={sidebarCollapsed}
            onMobileMenuOpen={() => setMobileOpen(true)}
            onSearchOpen={() => setSearchOpen(true)}
            userName={user.name}
          />
          <main className="app-content">{children}</main>
        </div>

        {/* Global Search Palette (Ctrl+K) */}
        {searchOpen && <SearchPalette />}
      </div>
    </WebSocketProvider>
  );
}
