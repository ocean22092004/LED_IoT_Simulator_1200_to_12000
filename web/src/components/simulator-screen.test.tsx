import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SimulatorScreen } from "./simulator-screen";
import { renderWithQuery } from "@/test/render-query";

function installSimulatorFetch() {
  const calls: Array<{ path: string; method: string; body: string | null }> = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const path = new URL(String(input)).pathname;
    const method = init?.method ?? "GET";
    calls.push({
      path,
      method,
      body: typeof init?.body === "string" ? init.body : null,
    });
    let body: unknown = { status: "ok" };
    if (path === "/api/v1/gateways") {
      body = [
        {
          id: "gateway-a",
          site_id: "site-1",
          zone_id: "zone-a",
          code: "GW-A",
          name: "Gateway A",
          status: "ONLINE",
          last_seen_at: null,
          firmware_version: null,
          is_simulated: true,
          affected_locations: 300,
        },
      ];
    } else if (path === "/api/v1/controllers") {
      body = [
        {
          id: "controller-a04",
          gateway_id: "gateway-a",
          gateway_code: "GW-A",
          code: "CTRL-A-04",
          address: 4,
          channel_capacity: 64,
          status: "OFFLINE",
          last_seen_at: null,
          is_active: true,
          affected_locations: 64,
        },
      ];
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  return calls;
}

it("keeps Simulator Lab unavailable to staff", () => {
  installSimulatorFetch();
  renderWithQuery(<SimulatorScreen role="STAFF" />);

  expect(screen.getByRole("alert")).toHaveTextContent("không có quyền");
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("exposes every simulator control to a technician and calls the control plane", async () => {
  const calls = installSimulatorFetch();
  const user = userEvent.setup();
  renderWithQuery(<SimulatorScreen role="TECHNICIAN" />);
  await screen.findByRole("heading", { name: "Simulator Lab" });

  await user.click(await screen.findByRole("button", { name: "Đưa Gateway offline" }));
  await user.click(screen.getByRole("button", { name: "Đưa Controller online" }));
  await user.type(screen.getByLabelText("Mã vị trí mô phỏng"), "A250");
  await user.click(screen.getByRole("button", { name: "Đốt bóng" }));
  await user.click(screen.getByRole("button", { name: "Xóa lỗi bóng" }));
  await user.click(screen.getByRole("button", { name: "Reset controller" }));
  await user.clear(screen.getByLabelText("ACK latency (ms)"));
  await user.type(screen.getByLabelText("ACK latency (ms)"), "750");
  await user.clear(screen.getByLabelText("ACK drop rate"));
  await user.type(screen.getByLabelText("ACK drop rate"), "0.25");
  await user.click(screen.getByRole("button", { name: "Lưu cấu hình ACK" }));

  expect(calls).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ path: "/api/v1/simulator/gateways/GW-A/offline", method: "POST" }),
      expect.objectContaining({ path: "/api/v1/simulator/controllers/CTRL-A-04/online", method: "POST" }),
      {
        path: "/api/v1/simulator/locations/A250/fault",
        method: "POST",
        body: JSON.stringify({ fault: "BURNED_OUT" }),
      },
      expect.objectContaining({ path: "/api/v1/simulator/locations/A250/fault", method: "DELETE" }),
      expect.objectContaining({ path: "/api/v1/simulator/controllers/CTRL-A-04/reset", method: "POST" }),
      {
        path: "/api/v1/simulator/settings",
        method: "POST",
        body: JSON.stringify({ command_latency_ms: 750, ack_drop_rate: 0.25 }),
      },
    ]),
  );
});
