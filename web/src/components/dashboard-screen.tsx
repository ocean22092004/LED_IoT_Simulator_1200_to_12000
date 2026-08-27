"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { queryKeys } from "@/lib/api/query-keys";
import {
  getAnniversariesToday,
  getDashboardSummary,
  getDeviceHealth,
  getFailedCommands,
} from "@/lib/api/queries";

const cards = [
  ["Tổng vị trí", "total_locations"],
  ["Đang yêu cầu sáng", "desired_on"],
  ["Actual ON", "actual_on"],
  ["Unknown", "actual_unknown"],
  ["Giỗ hôm nay", "anniversaries_today"],
  ["Đang thăm viếng", "active_visits"],
  ["Gateway Offline", "gateways_offline"],
  ["Controller Offline", "controllers_offline"],
  ["Nghi bóng hỏng", "suspected_failed_lamps"],
] as const;

export function DashboardScreen() {
  const summary = useQuery({
    queryKey: queryKeys.dashboardSummary,
    queryFn: getDashboardSummary,
  });
  const anniversaries = useQuery({
    queryKey: queryKeys.anniversariesToday,
    queryFn: getAnniversariesToday,
  });
  const health = useQuery({
    queryKey: queryKeys.deviceHealth,
    queryFn: getDeviceHealth,
  });
  const failedCommands = useQuery({
    queryKey: queryKeys.failedCommands,
    queryFn: getFailedCommands,
  });

  if (summary.isLoading || anniversaries.isLoading || health.isLoading || failedCommands.isLoading) {
    return <p role="status">Đang tải tổng quan…</p>;
  }
  if (!summary.data || !anniversaries.data || !health.data || !failedCommands.data) {
    return <p role="alert">Không thể tải dữ liệu tổng quan.</p>;
  }

  const warnings = [
    ...health.data.gateways
      .filter((gateway) => gateway.status === "OFFLINE")
      .map((gateway) => `${gateway.code} offline · ${gateway.affected_locations} vị trí ảnh hưởng`),
    ...health.data.controllers
      .filter((controller) => controller.status === "OFFLINE")
      .map(
        (controller) =>
          `${controller.code} offline · ${controller.affected_locations} vị trí ảnh hưởng`,
      ),
    ...failedCommands.data.items.map(
      (command) => `Lệnh ${command.location_code} thất bại · ${command.last_error ?? "Không rõ lỗi"}`,
    ),
    ...(summary.data.suspected_failed_lamps
      ? [`${summary.data.suspected_failed_lamps} bóng nghi hỏng`]
      : []),
  ];

  return (
    <div className="mx-auto max-w-[92rem] space-y-8">
      <div>
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-[var(--pine)]">
          Trung tâm vận hành
        </p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Tổng quan hệ thống</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">
          Desired và actual được theo dõi độc lập trên toàn bộ vị trí.
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-5">
        {cards.map(([label, field]) => (
          <article
            className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 shadow-sm"
            key={field}
          >
            <p className="text-sm font-semibold text-[var(--muted)]">{label}</p>
            <p className="mt-3 text-3xl font-semibold tabular-nums">
              {summary.data[field].toLocaleString("vi-VN")}
            </p>
          </article>
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Cảnh báo ưu tiên</h2>
            <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-800">
              {warnings.length} mục
            </span>
          </div>
          {warnings.length ? (
            <ul aria-label="Cảnh báo ưu tiên" className="mt-5 space-y-3">
              {warnings.map((warning) => (
                <li
                  className="rounded-2xl border border-red-900/10 bg-red-50/70 px-4 py-3 text-sm text-red-950"
                  key={warning}
                >
                  {warning}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-5 text-sm text-[var(--muted)]">Không có cảnh báo hoạt động.</p>
          )}
        </section>

        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold">Giỗ hôm nay</h2>
            <span className="text-sm font-semibold text-[var(--muted)]">
              {anniversaries.data.local_date}
            </span>
          </div>
          {anniversaries.data.items.length ? (
            <div className="mt-5 divide-y divide-stone-100">
              {anniversaries.data.items.map((item) => (
                <Link
                  className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"
                  href={`/locations/${item.location_id}`}
                  key={item.activation_id}
                >
                  <span>
                    <strong>{item.location_code}</strong>
                    <span className="ml-3 text-sm text-[var(--muted)]">
                      {item.person_name ?? "Chưa gán người"}
                    </span>
                  </span>
                  <span className="text-xs font-bold text-[var(--pine)]">Khu {item.zone_code}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="mt-5 text-sm text-[var(--muted)]">Không có lịch giỗ hôm nay.</p>
          )}
        </section>
      </div>
    </div>
  );
}
