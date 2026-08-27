import type { QueryClient, QueryKey } from "@tanstack/react-query";

import type { RealtimeEvent } from "./types";

const INVALIDATION_ROOTS: Record<RealtimeEvent["type"], QueryKey[]> = {
  "location.state_changed": [["locations"], ["dashboard"]],
  "lamp.health_changed": [["locations"], ["dashboard"]],
  "activation.changed": [["locations"], ["dashboard"]],
  "gateway.status_changed": [["devices"], ["dashboard"], ["locations"]],
  "controller.status_changed": [["devices"], ["dashboard"], ["locations"]],
  "command.failed": [["commands"], ["dashboard"], ["locations"]],
};

export async function invalidateForRealtimeEvent(
  queryClient: QueryClient,
  event: RealtimeEvent,
): Promise<void> {
  await Promise.all(
    INVALIDATION_ROOTS[event.type].map((queryKey) =>
      queryClient.invalidateQueries({ queryKey }),
    ),
  );
}
