import Link from "next/link";

import type { LocationSummary } from "@/lib/api/domain";
import { StateBadge } from "./state-badge";

export function LocationGridCard({ location }: { location: LocationSummary }) {
  return (
    <Link
      className="group rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 transition hover:-translate-y-0.5 hover:border-[var(--pine)] hover:shadow-lg"
      href={`/locations/${location.id}`}
    >
      <div className="flex items-center justify-between gap-2">
        <strong className="text-lg">{location.code}</strong>
        <StateBadge value={location.light.actual_state} />
      </div>
      <p className="mt-3 truncate text-sm text-[var(--muted)]">
        {location.person?.full_name ?? "Chưa gán người"}
      </p>
      <div className="mt-3 flex min-h-6 items-center justify-between gap-2 text-xs">
        <span>{location.hardware.controller_code} · {location.hardware.channel}</span>
        {location.light.lamp_health === "SUSPECTED_FAILED" ? (
          <span className="rounded-full bg-red-100 px-2 py-1 font-bold text-red-800">
            Nghi hỏng
          </span>
        ) : null}
      </div>
    </Link>
  );
}
