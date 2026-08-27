"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { queryKeys } from "@/lib/api/query-keys";
import {
  getControllerLocations,
  getControllers,
  getGateways,
} from "@/lib/api/queries";
import { LocationGridCard } from "./location-grid-card";
import { StateBadge } from "./state-badge";

export function DevicesScreen() {
  const [selectedController, setSelectedController] = useState("");
  const gateways = useQuery({ queryKey: queryKeys.gateways, queryFn: getGateways });
  const controllers = useQuery({
    queryKey: queryKeys.controllers,
    queryFn: getControllers,
  });
  const locations = useQuery({
    queryKey: queryKeys.controllerLocations(selectedController),
    queryFn: () => getControllerLocations(selectedController),
    enabled: Boolean(selectedController),
  });

  return (
    <div className="mx-auto max-w-[92rem] space-y-6">
      <header>
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-[var(--pine)]">Hạ tầng hiện trường</p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Thiết bị</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">Gateway → controller → vị trí được ánh xạ.</p>
      </header>

      <div className="grid gap-6 xl:grid-cols-[24rem_1fr]">
        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-5">
          <h2 className="text-lg font-semibold">Cây thiết bị</h2>
          {gateways.isLoading || controllers.isLoading ? <p className="mt-4" role="status">Đang tải thiết bị…</p> : null}
          <div className="mt-4 space-y-4">
            {(gateways.data ?? []).map((gateway) => (
              <article className="rounded-2xl border border-[var(--line)] bg-white p-4" key={gateway.id}>
                <div className="flex items-center justify-between gap-3">
                  <div><strong>{gateway.code}</strong><p className="mt-1 text-xs text-[var(--muted)]">{gateway.affected_locations} vị trí</p></div>
                  <StateBadge value={gateway.status} />
                </div>
                <div className="mt-3 space-y-2 border-l-2 border-stone-200 pl-3">
                  {(controllers.data ?? [])
                    .filter((controller) => controller.gateway_id === gateway.id)
                    .map((controller) => (
                      <button
                        aria-pressed={selectedController === controller.id}
                        className="flex w-full items-center justify-between gap-3 rounded-xl px-3 py-3 text-left hover:bg-stone-100 aria-pressed:bg-amber-50"
                        key={controller.id}
                        onClick={() => setSelectedController(controller.id)}
                        type="button"
                      >
                        <span><strong className="text-sm">{controller.code}</strong><span className="mt-1 block text-xs text-[var(--muted)]">{controller.affected_locations} vị trí</span></span>
                        <StateBadge value={controller.status} />
                      </button>
                    ))}
                </div>
              </article>
            ))}
          </div>
        </section>

        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-5">
          <h2 className="text-lg font-semibold">Vị trí ánh xạ</h2>
          {!selectedController ? (
            <p className="mt-4 text-sm text-[var(--muted)]">Chọn một controller để xem vị trí.</p>
          ) : locations.isLoading ? (
            <p className="mt-4" role="status">Đang tải mapping…</p>
          ) : (
            <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
              {(locations.data?.items ?? []).map((location) => (
                <LocationGridCard key={location.id} location={location} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
