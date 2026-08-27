"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  endActivation,
  manualOff,
  manualOn,
  startVisit,
  type VisitDuration,
} from "@/lib/api/actions";
import { ApiError } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/query-keys";
import { getLocation } from "@/lib/api/queries";
import type { UserRole } from "@/lib/api/types";
import { StateBadge } from "./state-badge";

function formatTime(value: string | null): string {
  if (!value) {
    return "Chưa có báo cáo";
  }
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "medium",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(new Date(value));
}

export function LocationDetailScreen({
  locationId,
  role,
}: {
  locationId: string;
  role: UserRole;
}) {
  const queryClient = useQueryClient();
  const [duration, setDuration] = useState<"30" | "60" | "120" | "240" | "null">(
    "60",
  );
  const [message, setMessage] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: queryKeys.locationDetail(locationId),
    queryFn: () => getLocation(locationId),
  });

  async function refreshRelated() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.locationDetail(locationId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      queryClient.invalidateQueries({ queryKey: queryKeys.commands }),
    ]);
  }

  const action = useMutation({
    mutationFn: async (request: {
      run: () => Promise<unknown>;
      success: string;
    }) => {
      await request.run();
      return request.success;
    },
    onSuccess: async (success) => {
      setMessage(success);
      await refreshRelated();
    },
    onError: (error) => {
      setMessage(
        error instanceof ApiError ? error.message : "Không thể thực hiện thao tác.",
      );
    },
  });

  if (detail.isLoading) {
    return <p role="status">Đang tải vị trí…</p>;
  }
  if (!detail.data) {
    return <p role="alert">Không thể tải chi tiết vị trí.</p>;
  }

  const location = detail.data;
  const activeVisit = location.active_activations.find(
    (activation) => activation.reason === "VISIT",
  );
  const canVisit = role === "STAFF" || role === "ADMIN";
  const canManual = role === "TECHNICIAN" || role === "ADMIN";
  const parsedDuration: VisitDuration = duration === "null" ? null : Number(duration) as VisitDuration;

  return (
    <div className="mx-auto max-w-7xl space-y-7">
      <header className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
        <div>
          <p className="text-sm font-bold uppercase tracking-[0.2em] text-[var(--pine)]">
            {location.zone.name}
          </p>
          <h1 className="mt-2 text-4xl font-semibold">{location.code}</h1>
          <p className="mt-2 text-lg text-[var(--muted)]">
            {location.person?.full_name ?? "Chưa gán người"}
          </p>
        </div>
        <p className="rounded-2xl border border-[var(--line)] bg-white px-4 py-3 text-sm font-semibold">
          {location.hardware.gateway_code} · {location.hardware.controller_code} · Kênh {location.hardware.channel}
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5" data-testid="desired-state">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Desired state</p>
          <div className="mt-4"><StateBadge value={location.light.desired_state} /></div>
        </article>
        <article className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5" data-testid="actual-state">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Actual state</p>
          <div className="mt-4"><StateBadge value={location.light.actual_state} /></div>
        </article>
        <article className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Sức khỏe bóng</p>
          <div className="mt-4"><StateBadge value={location.light.lamp_health} /></div>
          <p className="mt-3 text-sm font-semibold">
            {location.light.current_ma ? `${location.light.current_ma} mA` : "Không có dòng đo"}
          </p>
        </article>
        <article className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
          <p className="text-xs font-bold uppercase tracking-wider text-[var(--muted)]">Báo cáo cuối</p>
          <p className="mt-4 text-sm font-semibold">{formatTime(location.light.last_reported_at)}</p>
        </article>
      </section>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="space-y-6">
          <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
            <h2 className="text-xl font-semibold">Thông tin và lý do</h2>
            <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-[var(--muted)]">Ngày giỗ âm</dt>
                <dd className="mt-1 font-semibold">
                  {location.anniversary
                    ? `${location.anniversary.lunar_day}/${location.anniversary.lunar_month} âm lịch${location.anniversary.is_leap_month ? " · tháng nhuận" : ""}`
                    : "Chưa thiết lập"}
                </dd>
              </div>
              <div>
                <dt className="text-[var(--muted)]">Trạng thái vị trí</dt>
                <dd className="mt-1 font-semibold">{location.is_active ? "Đang hoạt động" : "Ngưng hoạt động"}</dd>
              </div>
            </dl>
            <div className="mt-5 flex flex-wrap gap-2" aria-label="Lý do đang hoạt động">
              {location.light.active_reasons.length ? (
                location.light.active_reasons.map((reason) => (
                  <span className="rounded-full bg-amber-100 px-3 py-1 text-xs font-bold text-amber-900" key={reason}>
                    {reason}
                  </span>
                ))
              ) : (
                <span className="text-sm text-[var(--muted)]">Không có lý do bật.</span>
              )}
            </div>
          </section>

          {(canVisit || canManual) ? (
            <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
              <h2 className="text-xl font-semibold">Điều khiển</h2>
              {canVisit ? (
                <div className="mt-5 rounded-2xl bg-stone-100 p-4">
                  <label className="text-sm font-semibold">
                    Thời lượng thăm viếng
                    <select
                      className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-3 py-2"
                      value={duration}
                      onChange={(event) => setDuration(event.target.value as typeof duration)}
                    >
                      <option value="30">30 phút</option>
                      <option value="60">60 phút</option>
                      <option value="120">120 phút</option>
                      <option value="240">240 phút</option>
                      <option value="null">Không giới hạn</option>
                    </select>
                  </label>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      className="rounded-xl bg-[var(--pine)] px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                      disabled={action.isPending}
                      onClick={() => action.mutate({
                        run: () => startVisit(locationId, parsedDuration),
                        success: "Đã bắt đầu thăm viếng",
                      })}
                      type="button"
                    >
                      Bắt đầu thăm viếng
                    </button>
                    {activeVisit ? (
                      <button
                        className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold disabled:opacity-50"
                        disabled={action.isPending}
                        onClick={() => action.mutate({
                          run: () => endActivation(activeVisit.id),
                          success: "Đã kết thúc thăm viếng",
                        })}
                        type="button"
                      >
                        Kết thúc thăm viếng
                      </button>
                    ) : null}
                  </div>
                </div>
              ) : null}
              {canManual ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  <button
                    className="rounded-xl bg-amber-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
                    disabled={action.isPending}
                    onClick={() => action.mutate({ run: () => manualOn(locationId), success: "Đã yêu cầu Manual ON" })}
                    type="button"
                  >
                    Manual ON
                  </button>
                  <button
                    className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold disabled:opacity-50"
                    disabled={action.isPending}
                    onClick={() => action.mutate({ run: () => manualOff(locationId), success: "Đã kết thúc Manual ON" })}
                    type="button"
                  >
                    Manual OFF
                  </button>
                </div>
              ) : null}
              {message ? <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm" role="status">{message}</p> : null}
            </section>
          ) : null}
        </div>

        <div className="space-y-6">
          <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
            <h2 className="text-xl font-semibold">Lệnh gần đây</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[36rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wider text-[var(--muted)]">
                  <tr><th className="pb-3">Mục tiêu</th><th className="pb-3">Trạng thái</th><th className="pb-3">Lý do</th><th className="pb-3">Thử</th></tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {location.recent_commands.map((command) => (
                    <tr key={command.id}>
                      <td className="py-3 font-semibold">{command.target_state}</td>
                      <td className="py-3">{command.status}</td>
                      <td className="py-3">{command.reason}</td>
                      <td className="py-3">{command.attempt_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
            <h2 className="text-xl font-semibold">Sự kiện thiết bị</h2>
            <ul className="mt-4 space-y-3">
              {location.recent_events.map((event) => (
                <li className="flex items-center justify-between rounded-xl bg-stone-100 px-4 py-3 text-sm" key={event.id}>
                  <strong>{event.event_type}</strong>
                  <span className="text-[var(--muted)]">{formatTime(event.occurred_at)}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
