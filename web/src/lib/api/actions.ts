import { apiRequest } from "./client";
import type { Activation } from "./domain";

export type VisitDuration = 30 | 60 | 120 | 240 | null;

export function startVisit(
  locationId: string,
  durationMinutes: VisitDuration,
): Promise<Activation> {
  return apiRequest<Activation>(`/api/v1/locations/${locationId}/visits`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: JSON.stringify({ duration_minutes: durationMinutes }),
  });
}

export function endActivation(activationId: string): Promise<Activation> {
  return apiRequest<Activation>(`/api/v1/activations/${activationId}/end`, {
    method: "POST",
  });
}

export function manualOn(locationId: string): Promise<Activation> {
  return apiRequest<Activation>(`/api/v1/locations/${locationId}/manual-on`, {
    method: "POST",
  });
}

export function manualOff(locationId: string): Promise<Activation> {
  return apiRequest<Activation>(`/api/v1/locations/${locationId}/manual-off`, {
    method: "POST",
  });
}

function simulatorRequest(
  path: string,
  method: "POST" | "DELETE" = "POST",
  body?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>(`/api/v1/simulator${path}`, {
    method,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
}

export function setGatewayOnline(code: string, online: boolean) {
  return simulatorRequest(`/gateways/${code}/${online ? "online" : "offline"}`);
}

export function setControllerOnline(code: string, online: boolean) {
  return simulatorRequest(`/controllers/${code}/${online ? "online" : "offline"}`);
}

export function setLocationFault(code: string, fault: "BURNED_OUT" | "STUCK_OFF") {
  return simulatorRequest(`/locations/${code}/fault`, "POST", { fault });
}

export function clearLocationFault(code: string) {
  return simulatorRequest(`/locations/${code}/fault`, "DELETE");
}

export function resetController(code: string) {
  return simulatorRequest(`/controllers/${code}/reset`);
}

export function setSimulatorSettings(commandLatencyMs: number, ackDropRate: number) {
  return simulatorRequest("/settings", "POST", {
    command_latency_ms: commandLatencyMs,
    ack_drop_rate: ackDropRate,
  });
}
