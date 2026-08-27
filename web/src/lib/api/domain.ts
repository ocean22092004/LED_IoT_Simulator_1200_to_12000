export type DeviceStatus = "ONLINE" | "OFFLINE" | "UNKNOWN";
export type DesiredState = "ON" | "OFF";
export type ActualState = "ON" | "OFF" | "UNKNOWN";
export type LampHealth = "OK" | "SUSPECTED_FAILED" | "UNKNOWN";
export type ActivationReason = "ANNIVERSARY" | "VISIT" | "MANUAL_ON";
export type CommandStatus = "PENDING" | "SENT" | "ACKED" | "FAILED";

export type LocationLightSummary = {
  desired_state: DesiredState;
  actual_state: ActualState;
  lamp_health: LampHealth;
};

export type LocationSummary = {
  id: string;
  site_id: string;
  code: string;
  zone: { code: string; name: string };
  person: { id: string; full_name: string } | null;
  hardware: {
    gateway_code: string;
    controller_code: string;
    channel: number;
  };
  light: LocationLightSummary;
  is_active: boolean;
};

export type PaginatedLocations = {
  items: LocationSummary[];
  page: number;
  page_size: number;
  total: number;
};

export type ActiveActivation = {
  id: string;
  reason: ActivationReason;
  starts_at: string;
  expires_at: string | null;
};

export type LocationCommand = {
  id: string;
  target_state: DesiredState;
  status: CommandStatus;
  reason: string;
  attempt_count: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
  acked_at: string | null;
};

export type LocationEvent = {
  id: number;
  event_type: string;
  occurred_at: string;
  received_at: string;
  payload: Record<string, unknown>;
};

export type LocationDetail = Omit<LocationSummary, "light"> & {
  anniversary: {
    lunar_day: number;
    lunar_month: number;
    is_leap_month: boolean;
  } | null;
  light: LocationLightSummary & {
    current_ma: string | null;
    active_reasons: ActivationReason[];
    last_reported_at: string | null;
  };
  active_activations: ActiveActivation[];
  recent_commands: LocationCommand[];
  recent_events: LocationEvent[];
};

export type Activation = {
  id: string;
  location_id: string;
  reason: ActivationReason;
  starts_at: string;
  expires_at: string | null;
  created_by_user_id: string | null;
  ended_at: string | null;
  created_at: string;
};

export type DashboardSummary = {
  total_locations: number;
  desired_on: number;
  actual_on: number;
  actual_unknown: number;
  anniversaries_today: number;
  active_visits: number;
  gateways_online: number;
  gateways_offline: number;
  controllers_online: number;
  controllers_offline: number;
  suspected_failed_lamps: number;
};

export type AnniversaryToday = {
  activation_id: string;
  location_id: string;
  location_code: string;
  person_id: string | null;
  person_name: string | null;
  zone_code: string;
  starts_at: string;
  expires_at: string | null;
};

export type DashboardAnniversaries = {
  local_date: string;
  total: number;
  items: AnniversaryToday[];
};

export type GatewayHealth = {
  id: string;
  code: string;
  name: string;
  status: DeviceStatus;
  last_seen_at: string | null;
  affected_locations: number;
};

export type ControllerHealth = {
  id: string;
  gateway_id: string;
  gateway_code: string;
  code: string;
  address: number;
  status: DeviceStatus;
  last_seen_at: string | null;
  affected_locations: number;
};

export type DeviceHealth = {
  gateways: GatewayHealth[];
  controllers: ControllerHealth[];
};

export type Command = {
  id: string;
  location_id: string;
  location_code: string;
  gateway_id: string;
  gateway_code: string;
  controller_id: string;
  controller_code: string;
  channel_number: number;
  target_state: DesiredState;
  status: CommandStatus;
  reason: string;
  attempt_count: number;
  next_attempt_at: string;
  sent_at: string | null;
  acked_at: string | null;
  last_error: string | null;
  created_at: string;
};

export type PaginatedCommands = {
  items: Command[];
  page: number;
  page_size: number;
  total: number;
};

export type Zone = {
  id: string;
  site_id: string;
  code: string;
  name: string;
  sort_order: number;
  is_active: boolean;
};

export type Gateway = GatewayHealth & {
  site_id: string;
  zone_id: string | null;
  firmware_version: string | null;
  is_simulated: boolean;
};

export type Controller = ControllerHealth & {
  channel_capacity: number;
  is_active: boolean;
};
