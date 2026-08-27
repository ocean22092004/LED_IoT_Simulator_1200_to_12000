"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { queryKeys } from "@/lib/api/query-keys";
import { getZoneLocations, getZones } from "@/lib/api/queries";
import { LocationGridCard } from "./location-grid-card";

const PAGE_SIZE = 100;

export function ZoneGridScreen() {
  const [selected, setSelected] = useState("");
  const [page, setPage] = useState(1);
  const zones = useQuery({ queryKey: queryKeys.zones, queryFn: getZones });
  const zoneId = selected || zones.data?.find((zone) => zone.is_active)?.id || "";
  const locations = useQuery({
    queryKey: queryKeys.zoneLocations(zoneId, page),
    queryFn: () => getZoneLocations(zoneId, page),
    enabled: Boolean(zoneId),
  });
  const pages = Math.max(1, Math.ceil((locations.data?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="mx-auto max-w-[92rem] space-y-6">
      <header className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-[var(--pine)]">Bản đồ trạng thái</p>
          <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Lưới khu vực</h1>
          <p className="mt-2 text-sm text-[var(--muted)]">Tải theo trang để giữ giao diện ổn định ở quy mô 12.000 vị trí.</p>
        </div>
        <label className="text-sm font-semibold">
          Chọn khu vực
          <select
            className="ml-3 rounded-xl border border-[var(--line)] bg-white px-4 py-2"
            value={zoneId}
            onChange={(event) => {
              setSelected(event.target.value);
              setPage(1);
            }}
          >
            {(zones.data ?? []).map((zone) => (
              <option key={zone.id} value={zone.id}>{zone.name}</option>
            ))}
          </select>
        </label>
      </header>

      {zones.isLoading || locations.isLoading ? <p role="status">Đang tải lưới…</p> : null}
      {locations.data ? (
        <>
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-7 2xl:grid-cols-10">
            {locations.data.items.map((location) => (
              <LocationGridCard key={location.id} location={location} />
            ))}
          </section>
          <nav aria-label="Phân trang khu vực" className="flex items-center justify-center gap-4">
            <button
              className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold disabled:opacity-40"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              Trang trước
            </button>
            <span className="text-sm font-semibold">Trang {page} / {pages}</span>
            <button
              className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold disabled:opacity-40"
              disabled={page >= pages}
              onClick={() => setPage((current) => Math.min(pages, current + 1))}
              type="button"
            >
              Trang sau
            </button>
          </nav>
        </>
      ) : null}
    </div>
  );
}
