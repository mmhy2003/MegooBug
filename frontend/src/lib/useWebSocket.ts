import { useEffect, useRef, useState, useCallback } from "react";

export type WSStatus = "connecting" | "connected" | "disconnected";

export interface WebSocketMessage {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

/**
 * React hook for a WebSocket connection to /ws/notifications.
 *
 * Provides:
 *  - `status`      Connection state
 *  - `lastMessage` Most recent message received
 *  - `subscribe`   Join a project channel
 *  - `unsubscribe` Leave a project channel
 *  - `sendMessage` Send raw JSON to the server
 */
export function useWebSocket() {
  const [status, setStatus] = useState<WSStatus>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(1000);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");

    const ws = new WebSocket(`${WS_URL}/ws/notifications`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setStatus("connected");
      backoffRef.current = 1000; // Reset backoff on success
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const data = JSON.parse(event.data) as WebSocketMessage;

        // Respond to server heartbeat pings
        if (data.type === "ping") {
          ws.send(JSON.stringify({ type: "pong" }));
          return;
        }

        setLastMessage(data);
      } catch {
        // Ignore unparseable messages
      }
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      wsRef.current = null;

      // Don't reconnect if the close was a 4001 (auth failure)
      if (event.code === 4001) return;

      // Exponential backoff reconnect
      const delay = Math.min(backoffRef.current, 30000);
      backoffRef.current = delay * 2;
      reconnectTimer.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose will fire next — handled there
    };
  }, []);

  const sendMessage = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const subscribe = useCallback(
    (channel: "project", id: string) => {
      sendMessage({ action: "subscribe", channel, id });
    },
    [sendMessage]
  );

  const unsubscribe = useCallback(
    (channel: "project", id: string) => {
      sendMessage({ action: "unsubscribe", channel, id });
    },
    [sendMessage]
  );

  // Connect on mount, cleanup on unmount
  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  return { status, lastMessage, subscribe, unsubscribe, sendMessage };
}
