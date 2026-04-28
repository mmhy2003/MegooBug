"use client";

import React, { createContext, useContext } from "react";
import { useWebSocket, WSStatus, WebSocketMessage } from "@/lib/useWebSocket";

interface WebSocketContextValue {
  status: WSStatus;
  lastMessage: WebSocketMessage | null;
  subscribe: (channel: "project", id: string) => void;
  unsubscribe: (channel: "project", id: string) => void;
}

const WebSocketContext = createContext<WebSocketContextValue>({
  status: "disconnected",
  lastMessage: null,
  subscribe: () => {},
  unsubscribe: () => {},
});

/**
 * Provides a single shared WebSocket connection to all dashboard components.
 * Wrap the dashboard layout with this provider.
 */
export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const ws = useWebSocket();

  return (
    <WebSocketContext.Provider value={ws}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * Access the shared WebSocket connection from any dashboard component.
 */
export function useWS() {
  return useContext(WebSocketContext);
}
