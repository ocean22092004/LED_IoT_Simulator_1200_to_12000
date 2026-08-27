import { parseRealtimeEvent, type RealtimeEvent } from "./types";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

type SocketLike = {
  onmessage: ((event: MessageEvent<string>) => void) | null;
  onclose: (() => void) | null;
  close: () => void;
};

type SocketConstructor = new (url: string) => SocketLike;

export function connectRealtime(
  token: string,
  onEvent: (event: RealtimeEvent) => void,
  options: {
    WebSocketImpl?: SocketConstructor;
    reconnectMs?: number;
  } = {},
): () => void {
  const WebSocketImpl = options.WebSocketImpl ?? (WebSocket as SocketConstructor);
  const reconnectMs = options.reconnectMs ?? 1_000;
  let stopped = false;
  let socket: SocketLike | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let reconnectAttempt = 0;

  function open() {
    if (stopped) {
      return;
    }
    socket = new WebSocketImpl(
      `${WS_URL}/api/v1/ws/events?token=${encodeURIComponent(token)}`,
    );
    socket.onmessage = (message) => {
      const event = parseRealtimeEvent(message.data);
      if (event) {
        onEvent(event);
      }
    };
    socket.onclose = () => {
      if (stopped) {
        return;
      }
      const delay = Math.min(reconnectMs * 2 ** reconnectAttempt, 10_000);
      reconnectAttempt += 1;
      reconnectTimer = setTimeout(open, delay);
    };
  }

  open();
  return () => {
    stopped = true;
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
    }
    socket?.close();
  };
}
