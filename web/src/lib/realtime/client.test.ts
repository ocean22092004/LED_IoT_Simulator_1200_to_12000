import { connectRealtime } from "./client";
import type { RealtimeEvent } from "./types";

class FakeSocket {
  static instances: FakeSocket[] = [];
  readonly url: string;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

it("authenticates, forwards valid deltas, reconnects, and stops cleanly", () => {
  const events: RealtimeEvent[] = [];
  const disconnect = connectRealtime("jwt value", (event) => events.push(event), {
    WebSocketImpl: FakeSocket,
    reconnectMs: 1000,
  });
  expect(FakeSocket.instances[0].url).toBe(
    "ws://localhost:8000/api/v1/ws/events?token=jwt%20value",
  );
  FakeSocket.instances[0].onmessage?.(
    new MessageEvent("message", {
      data: JSON.stringify({
        id: "event-1",
        type: "location.state_changed",
        occurred_at: "2026-08-27T04:00:00Z",
        entity_type: "location",
        entity_id: "location-a250",
        payload: { actual_state: "ON" },
      }),
    }),
  );
  expect(events).toHaveLength(1);

  FakeSocket.instances[0].onclose?.();
  vi.advanceTimersByTime(1000);
  expect(FakeSocket.instances).toHaveLength(2);

  disconnect();
  FakeSocket.instances[1].onclose?.();
  vi.advanceTimersByTime(5000);
  expect(FakeSocket.instances).toHaveLength(2);
  expect(FakeSocket.instances[1].close).toHaveBeenCalled();
});
