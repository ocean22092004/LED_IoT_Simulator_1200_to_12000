import { apiRequest } from "./client";
import type {
  DashboardAnniversaries,
  DashboardSummary,
  DeviceHealth,
  Gateway,
  LocationDetail,
  PaginatedCommands,
  PaginatedLocations,
  Controller,
  Zone,
} from "./domain";

export function searchLocations(search: string): Promise<PaginatedLocations> {
  const params = new URLSearchParams({ search, page: "1", page_size: "8" });
  return apiRequest<PaginatedLocations>(`/api/v1/locations?${params}`);
}

export function getLocation(locationId: string): Promise<LocationDetail> {
  return apiRequest<LocationDetail>(`/api/v1/locations/${locationId}`);
}

export function getDashboardSummary(): Promise<DashboardSummary> {
  return apiRequest<DashboardSummary>("/api/v1/dashboard/summary");
}

export function getAnniversariesToday(): Promise<DashboardAnniversaries> {
  return apiRequest<DashboardAnniversaries>(
    "/api/v1/dashboard/anniversaries-today",
  );
}

export function getDeviceHealth(): Promise<DeviceHealth> {
  return apiRequest<DeviceHealth>("/api/v1/dashboard/device-health");
}

export function getFailedCommands(): Promise<PaginatedCommands> {
  return apiRequest<PaginatedCommands>(
    "/api/v1/commands?status=FAILED&page=1&page_size=10",
  );
}

export function getZones(): Promise<Zone[]> {
  return apiRequest<Zone[]>("/api/v1/zones");
}

export function getZoneLocations(
  zoneId: string,
  page: number,
): Promise<PaginatedLocations> {
  const params = new URLSearchParams({ page: String(page), page_size: "100" });
  return apiRequest<PaginatedLocations>(
    `/api/v1/zones/${zoneId}/locations?${params}`,
  );
}

export function getGateways(): Promise<Gateway[]> {
  return apiRequest<Gateway[]>("/api/v1/gateways");
}

export function getControllers(): Promise<Controller[]> {
  return apiRequest<Controller[]>("/api/v1/controllers");
}

export function getControllerLocations(
  controllerId: string,
): Promise<PaginatedLocations> {
  const params = new URLSearchParams({
    controller_id: controllerId,
    page: "1",
    page_size: "100",
  });
  return apiRequest<PaginatedLocations>(`/api/v1/locations?${params}`);
}
