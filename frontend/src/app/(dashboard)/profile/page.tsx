"use client";

import { Suspense } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCurrentUser } from "@/components/current-user-provider";
import { NotificationPreferences } from "@/components/profile/notification-preferences";
import { ApiKeys } from "@/components/profile/api-keys";
import { AccountForms } from "@/components/profile/account-forms";
import { SecuritySettings } from "@/components/profile/security-settings";

const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  developer: "Developer",
  viewer: "Viewer",
};

const TABS = [
  { key: "account", label: "Account", roles: ["admin", "developer", "viewer"] },
  { key: "security", label: "Security", roles: ["admin", "developer", "viewer"] },
  { key: "notifications", label: "Notifications", roles: ["admin", "developer", "viewer"] },
  { key: "apikeys", label: "API Keys", roles: ["admin", "developer"] },
];

export default function ProfilePage() {
  const { user } = useCurrentUser();

  const memberSince = new Date(user.created_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div style={{ maxWidth: "820px", margin: "0 auto" }}>
      <div className="page-header">
        <div>
          <h1 className="page-title">Profile</h1>
          <p className="text-muted" style={{ fontSize: "0.875rem", marginTop: "0.25rem" }}>
            Manage your personal details, password, security, notifications and API keys.
          </p>
        </div>
      </div>

      {/* Summary banner */}
      <div
        className="card"
        style={{
          display: "flex",
          flexWrap: "wrap",
          alignItems: "center",
          gap: "1.25rem",
          marginBottom: "1.5rem",
        }}
      >
        <div
          className="user-avatar"
          aria-hidden="true"
          style={{ width: "72px", height: "72px", fontSize: "1.875rem", cursor: "default" }}
        >
          {user.name.charAt(0).toUpperCase()}
        </div>
        <div style={{ flex: "1 1 200px", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 600, overflowWrap: "anywhere" }}>
              {user.name}
            </h2>
            <span
              style={{
                padding: "0.125rem 0.625rem",
                borderRadius: "999px",
                fontSize: "0.75rem",
                fontWeight: 600,
                color: "var(--accent-primary)",
                background: "rgba(var(--accent-primary-rgb), 0.1)",
                border: "1px solid rgba(var(--accent-primary-rgb), 0.3)",
              }}
            >
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </div>
          <p className="text-muted" style={{ fontSize: "0.875rem", marginTop: "0.25rem", overflowWrap: "anywhere" }}>
            {user.email}
          </p>
        </div>
        <div style={{ fontSize: "0.8125rem", textAlign: "right" }}>
          <div className="text-muted">Member since</div>
          <div>{memberSince}</div>
        </div>
      </div>

      <Suspense fallback={null}>
        <ProfileTabs role={user.role} />
      </Suspense>
    </div>
  );
}

/** Tab bar + content; the active tab lives in `?tab=` so it can be linked. */
function ProfileTabs({ role }: { role: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const visibleTabs = TABS.filter((tab) => tab.roles.includes(role));
  const requested = searchParams.get("tab");
  const activeTab = visibleTabs.some((t) => t.key === requested) ? requested : "account";

  return (
    <>
      <div className="tabs" role="tablist" aria-label="Profile sections">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            className={`tab ${activeTab === tab.key ? "active" : ""}`}
            onClick={() => router.replace(`${pathname}?tab=${tab.key}`, { scroll: false })}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "account" && <AccountForms />}
      {activeTab === "security" && <SecuritySettings />}
      {activeTab === "notifications" && <NotificationPreferences />}
      {activeTab === "apikeys" && <ApiKeys />}
    </>
  );
}
