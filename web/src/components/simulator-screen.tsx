"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  clearLocationFault,
  resetController,
  setControllerOnline,
  setGatewayOnline,
  setLocationFault,
  setSimulatorSettings,
} from "@/lib/api/actions";
import { ApiError } from "@/lib/api/client";
import { queryKeys } from "@/lib/api/query-keys";
import { getControllers, getGateways } from "@/lib/api/queries";
import type { UserRole } from "@/lib/api/types";
import { StateBadge } from "./state-badge";

export function SimulatorScreen({ role }: { role: UserRole }) {
  const queryClient = useQueryClient();
  const enabled = role === "ADMIN" || role === "TECHNICIAN";
  const gateways = useQuery({
    queryKey: queryKeys.gateways,
    queryFn: getGateways,
    enabled,
  });
  const controllers = useQuery({
    queryKey: queryKeys.controllers,
    queryFn: getControllers,
    enabled,
  });
  const [gatewayCode, setGatewayCode] = useState("");
  const [controllerCode, setControllerCode] = useState("");
  const [locationCode, setLocationCode] = useState("");
  const [latency, setLatency] = useState("0");
  const [dropRate, setDropRate] = useState("0");
  const [message, setMessage] = useState<string | null>(null);
  const selectedGatewayCode = gatewayCode || gateways.data?.[0]?.code || "";
  const selectedControllerCode = controllerCode || controllers.data?.[0]?.code || "";
  const selectedGateway = gateways.data?.find(
    (gateway) => gateway.code === selectedGatewayCode,
  );
  const selectedController = controllers.data?.find(
    (controller) => controller.code === selectedControllerCode,
  );
  const mutation = useMutation({
    mutationFn: async (request: { run: () => Promise<unknown>; success: string }) => {
      await request.run();
      return request.success;
    },
    onSuccess: async (success) => {
      setMessage(success);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["devices"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["locations"] }),
      ]);
    },
    onError: (error) => {
      setMessage(error instanceof ApiError ? error.message : "Thao tác simulator thất bại");
    },
  });

  if (!enabled) {
    return <p role="alert">Tài khoản này không có quyền truy cập Simulator Lab.</p>;
  }

  function run(run: () => Promise<unknown>, success: string) {
    mutation.mutate({ run, success });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-7">
      <header>
        <p className="text-sm font-bold uppercase tracking-[0.2em] text-amber-700">Môi trường mô phỏng</p>
        <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Simulator Lab</h1>
        <p className="mt-2 text-sm text-[var(--muted)]">Bơm lỗi qua control plane nội bộ; browser không kết nối MQTT.</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
          <h2 className="text-xl font-semibold">Gateway và controller</h2>
          <label className="mt-5 block text-sm font-semibold">
            Gateway
            <select className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3" value={selectedGatewayCode} onChange={(event) => setGatewayCode(event.target.value)}>
              {(gateways.data ?? []).map((gateway) => <option key={gateway.id} value={gateway.code}>{gateway.code}</option>)}
            </select>
          </label>
          {selectedGateway ? <div className="mt-3"><StateBadge value={selectedGateway.status} /></div> : null}
          <button
            className="mt-3 rounded-xl bg-[var(--pine)] px-4 py-2 text-sm font-bold text-white"
            onClick={() => run(
              () => setGatewayOnline(selectedGatewayCode, selectedGateway?.status !== "ONLINE"),
              "Đã cập nhật gateway",
            )}
            type="button"
          >
            {selectedGateway?.status === "ONLINE" ? "Đưa Gateway offline" : "Đưa Gateway online"}
          </button>

          <label className="mt-6 block text-sm font-semibold">
            Controller
            <select className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3" value={selectedControllerCode} onChange={(event) => setControllerCode(event.target.value)}>
              {(controllers.data ?? []).map((controller) => <option key={controller.id} value={controller.code}>{controller.code}</option>)}
            </select>
          </label>
          {selectedController ? <div className="mt-3"><StateBadge value={selectedController.status} /></div> : null}
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-xl bg-[var(--pine)] px-4 py-2 text-sm font-bold text-white"
              onClick={() => run(
                () => setControllerOnline(selectedControllerCode, selectedController?.status !== "ONLINE"),
                "Đã cập nhật controller",
              )}
              type="button"
            >
              {selectedController?.status === "ONLINE" ? "Đưa Controller offline" : "Đưa Controller online"}
            </button>
            <button className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold" onClick={() => run(() => resetController(selectedControllerCode), "Đã reset controller")} type="button">
              Reset controller
            </button>
          </div>
        </section>

        <section className="rounded-3xl border border-[var(--line)] bg-[var(--surface)] p-6">
          <h2 className="text-xl font-semibold">Lỗi bóng đèn</h2>
          <label className="mt-5 block text-sm font-semibold">
            Mã vị trí mô phỏng
            <input className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3 uppercase" placeholder="A250" value={locationCode} onChange={(event) => setLocationCode(event.target.value.toUpperCase())} />
          </label>
          <div className="mt-4 flex flex-wrap gap-2">
            <button className="rounded-xl bg-red-700 px-4 py-2 text-sm font-bold text-white" onClick={() => run(() => setLocationFault(locationCode, "BURNED_OUT"), "Đã đặt lỗi cháy bóng")} type="button">Đốt bóng</button>
            <button className="rounded-xl border border-[var(--line)] bg-white px-4 py-2 text-sm font-bold" onClick={() => run(() => clearLocationFault(locationCode), "Đã xóa lỗi bóng")} type="button">Xóa lỗi bóng</button>
          </div>

          <h2 className="mt-8 text-xl font-semibold">Mô phỏng ACK</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-semibold">ACK latency (ms)<input className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3" min="0" type="number" value={latency} onChange={(event) => setLatency(event.target.value)} /></label>
            <label className="text-sm font-semibold">ACK drop rate<input className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3" max="1" min="0" step="0.01" type="number" value={dropRate} onChange={(event) => setDropRate(event.target.value)} /></label>
          </div>
          <button className="mt-4 rounded-xl bg-amber-600 px-4 py-2 text-sm font-bold text-white" onClick={() => run(() => setSimulatorSettings(Number(latency), Number(dropRate)), "Đã lưu cấu hình ACK")} type="button">Lưu cấu hình ACK</button>
        </section>
      </div>
      {message ? <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm" role="status">{message}</p> : null}
    </div>
  );
}
