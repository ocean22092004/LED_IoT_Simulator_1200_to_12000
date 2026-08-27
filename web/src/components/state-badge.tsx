import type { ActualState, DesiredState, DeviceStatus, LampHealth } from "@/lib/api/domain";

type StateValue = ActualState | DesiredState | DeviceStatus | LampHealth;

const styles: Record<StateValue, string> = {
  ON: "border-emerald-700/20 bg-emerald-50 text-emerald-800",
  OFF: "border-stone-400/30 bg-stone-100 text-stone-700",
  ONLINE: "border-emerald-700/20 bg-emerald-50 text-emerald-800",
  OFFLINE: "border-red-700/20 bg-red-50 text-red-800",
  UNKNOWN: "border-amber-700/20 bg-amber-50 text-amber-900",
  OK: "border-emerald-700/20 bg-emerald-50 text-emerald-800",
  SUSPECTED_FAILED: "border-red-700/20 bg-red-50 text-red-800",
};

export function StateBadge({ value }: { value: StateValue }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold tracking-wide ${styles[value]}`}
    >
      {value}
    </span>
  );
}
