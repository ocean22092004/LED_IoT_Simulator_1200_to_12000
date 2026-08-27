export type RealtimeEventType =
  | "location.state_changed"
  | "gateway.status_changed"
  | "controller.status_changed"
  | "command.failed"
  | "lamp.health_changed"
  | "activation.changed";

export type RealtimeEvent = {
  id: string;
  type: RealtimeEventType;
  occurred_at: string;
  entity_type: string;
  entity_id: string | null;
  payload: Record<string, unknown>;
};

const EVENT_TYPES = new Set<RealtimeEventType>([
  "location.state_changed",
  "gateway.status_changed",
  "controller.status_changed",
  "command.failed",
  "lamp.health_changed",
  "activation.changed",
]);

export function parseRealtimeEvent(value: string): RealtimeEvent | null {
  try {
    const parsed: unknown = JSON.parse(value);
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      !("type" in parsed) ||
      typeof parsed.type !== "string" ||
      !EVENT_TYPES.has(parsed.type as RealtimeEventType) ||
      !("payload" in parsed) ||
      typeof parsed.payload !== "object" ||
      parsed.payload === null
    ) {
      return null;
    }
    return parsed as RealtimeEvent;
  } catch {
    return null;
  }
}
