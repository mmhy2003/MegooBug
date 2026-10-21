"use client";

import { createContext, useContext } from "react";

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  role: "admin" | "developer" | "viewer";
  created_at: string;
}

interface CurrentUserContextValue {
  user: CurrentUser;
  setUser: (user: CurrentUser) => void;
}

const CurrentUserContext = createContext<CurrentUserContextValue | null>(null);

/** Shares the signed-in user (loaded by the dashboard layout) with pages. */
export function CurrentUserProvider({
  user,
  onUserChange,
  children,
}: {
  user: CurrentUser;
  onUserChange: (user: CurrentUser) => void;
  children: React.ReactNode;
}) {
  return (
    <CurrentUserContext.Provider value={{ user, setUser: onUserChange }}>
      {children}
    </CurrentUserContext.Provider>
  );
}

export function useCurrentUser(): CurrentUserContextValue {
  const ctx = useContext(CurrentUserContext);
  if (!ctx) {
    throw new Error("useCurrentUser must be used inside CurrentUserProvider");
  }
  return ctx;
}
