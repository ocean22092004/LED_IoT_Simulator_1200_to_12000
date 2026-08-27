import { QueryClient } from "@tanstack/react-query";

import { invalidateForRealtimeEvent } from "./invalidation";
import type { RealtimeEvent, RealtimeEventType } from "./types";

const cases: Array<[RealtimeEventType, readonly unknown[]]> = [
  ["location.state_changed", ["locations"]],
  ["lamp.health_changed", ["locations"]],
  ["activation.changed", ["dashboard"]],
  ["gateway.status_changed", ["devices"]],
  ["controller.status_changed", ["devices"]],
  ["command.failed", ["commands"]],
];

it.each(cases)("invalidates relevant cached data for %s", async (type, expectedKey) => {
  const queryClient = new QueryClient();
  const keys = [
    ["locations"],
    ["dashboard"],
    ["devices"],
    ["commands"],
  ] as const;
  for (const key of keys) {
    queryClient.setQueryData(key, { value: key[0] });
  }
  const event: RealtimeEvent = {
    id: "event-1",
    type,
    occurred_at: "2026-08-27T04:00:00Z",
    entity_type: type.startsWith("location") ? "location" : "device",
    entity_id: "entity-1",
    payload: { location_id: "location-a250" },
  };

  await invalidateForRealtimeEvent(queryClient, event);

  expect(queryClient.getQueryState(expectedKey)?.isInvalidated).toBe(true);
});

it("invalidates controller mappings so an offline event can refetch without reload", async () => {
  const queryClient = new QueryClient();
  queryClient.setQueryData(["locations", "controller", "controller-a04"], {
    items: [],
  });
  queryClient.setQueryData(["dashboard", "device-health"], { controllers: [] });

  await invalidateForRealtimeEvent(queryClient, {
    id: "event-controller",
    type: "controller.status_changed",
    occurred_at: "2026-08-27T04:00:00Z",
    entity_type: "controller",
    entity_id: "controller-a04",
    payload: { status: "OFFLINE" },
  });

  expect(
    queryClient.getQueryState(["locations", "controller", "controller-a04"])
      ?.isInvalidated,
  ).toBe(true);
  expect(
    queryClient.getQueryState(["dashboard", "device-health"])?.isInvalidated,
  ).toBe(true);
});
