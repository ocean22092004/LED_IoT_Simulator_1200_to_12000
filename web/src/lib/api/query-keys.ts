export const queryKeys = {
  dashboard: ["dashboard"] as const,
  dashboardSummary: ["dashboard", "summary"] as const,
  anniversariesToday: ["dashboard", "anniversaries-today"] as const,
  deviceHealth: ["dashboard", "device-health"] as const,
  locations: ["locations"] as const,
  locationSearch: (search: string) => ["locations", "search", search] as const,
  locationDetail: (locationId: string) => ["locations", "detail", locationId] as const,
  commands: ["commands"] as const,
  failedCommands: ["commands", "failed"] as const,
  zones: ["zones"] as const,
  zoneLocations: (zoneId: string, page: number) =>
    ["locations", "zone", zoneId, page] as const,
  gateways: ["devices", "gateways"] as const,
  controllers: ["devices", "controllers"] as const,
  controllerLocations: (controllerId: string) =>
    ["locations", "controller", controllerId] as const,
};
