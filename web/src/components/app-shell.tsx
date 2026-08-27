"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import type { AuthUser } from "@/lib/api/types";
import { queryKeys } from "@/lib/api/query-keys";
import { searchLocations } from "@/lib/api/queries";
import { useDebouncedValue } from "@/lib/hooks/use-debounced-value";
import { StateBadge } from "./state-badge";

const navigation = [
  { href: "/", label: "Tổng quan" },
  { href: "/zones", label: "Khu vực" },
  { href: "/devices", label: "Thiết bị" },
];

export function AppShell({
  user,
  onLogout,
  children,
}: {
  user: AuthUser;
  onLogout: () => void;
  children: ReactNode;
}) {
  const router = useRouter();
  const [term, setTerm] = useState("");
  const debouncedTerm = useDebouncedValue(term.trim(), 250);
  const result = useQuery({
    queryKey: queryKeys.locationSearch(debouncedTerm),
    queryFn: () => searchLocations(debouncedTerm),
    enabled: debouncedTerm.length >= 2,
  });
  const canUseSimulator = user.role === "ADMIN" || user.role === "TECHNICIAN";

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[15.5rem_1fr]">
      <aside className="bg-[var(--pine-dark)] px-5 py-6 text-stone-100 lg:min-h-screen lg:px-6 lg:py-8">
        <div className="flex items-center justify-between lg:block">
          <Link className="text-lg font-bold tracking-tight" href="/">
            Memorial IoT
          </Link>
          <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-amber-200">
            {user.role}
          </span>
        </div>
        <nav
          aria-label="Điều hướng chính"
          className="mt-6 flex gap-2 overflow-x-auto lg:mt-10 lg:flex-col"
        >
          {navigation.map((item) => (
            <Link
              className="whitespace-nowrap rounded-xl px-4 py-3 text-sm font-semibold text-stone-200 transition hover:bg-white/10 hover:text-white"
              href={item.href}
              key={item.href}
            >
              {item.label}
            </Link>
          ))}
          {canUseSimulator ? (
            <Link
              className="whitespace-nowrap rounded-xl px-4 py-3 text-sm font-semibold text-amber-200 transition hover:bg-white/10"
              href="/simulator"
            >
              Simulator Lab
            </Link>
          ) : null}
        </nav>
        <button
          className="mt-6 rounded-xl border border-white/15 px-4 py-2 text-sm text-stone-300 hover:bg-white/10 lg:mt-12"
          onClick={onLogout}
          type="button"
        >
          Đăng xuất · {user.username}
        </button>
      </aside>
      <div className="min-w-0">
        <header className="relative border-b border-[var(--line)] bg-[rgba(255,253,247,0.86)] px-5 py-4 backdrop-blur md:px-8">
          <label className="mx-auto block max-w-3xl text-xs font-bold uppercase tracking-[0.18em] text-[var(--muted)]">
            Tìm vị trí hoặc tên người
            <input
              className="mt-2 w-full rounded-2xl border border-[var(--line)] bg-white px-5 py-3 text-base font-normal normal-case tracking-normal outline-none focus:border-[var(--pine)] focus:ring-4 focus:ring-emerald-900/10"
              placeholder="Ví dụ: A250 hoặc tên người"
              value={term}
              onChange={(event) => setTerm(event.target.value)}
            />
          </label>
          {debouncedTerm.length >= 2 ? (
            <div className="absolute left-5 right-5 top-[6.3rem] z-30 mx-auto max-w-3xl overflow-hidden rounded-2xl border border-[var(--line)] bg-white shadow-2xl md:left-8 md:right-8">
              {result.isLoading ? (
                <p className="px-5 py-4 text-sm text-[var(--muted)]">Đang tìm…</p>
              ) : result.isError ? (
                <p className="px-5 py-4 text-sm text-red-700">Không thể tìm kiếm.</p>
              ) : result.data?.items.length ? (
                result.data.items.map((location) => (
                  <button
                    className="flex w-full items-center justify-between gap-4 border-b border-stone-100 px-5 py-4 text-left last:border-0 hover:bg-stone-50"
                    key={location.id}
                    onClick={() => {
                      setTerm("");
                      router.push(`/locations/${location.id}`);
                    }}
                    type="button"
                  >
                    <span>
                      <strong>{location.code}</strong>
                      <span className="ml-3 text-sm text-[var(--muted)]">
                        {location.person?.full_name ?? "Chưa gán người"} · {location.zone.name}
                      </span>
                    </span>
                    <StateBadge value={location.light.actual_state} />
                  </button>
                ))
              ) : (
                <p className="px-5 py-4 text-sm text-[var(--muted)]">Không có kết quả.</p>
              )}
            </div>
          ) : null}
        </header>
        <main className="px-5 py-7 md:px-8 md:py-9">{children}</main>
      </div>
    </div>
  );
}
