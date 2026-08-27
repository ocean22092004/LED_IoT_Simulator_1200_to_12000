import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DevicesScreen } from "./devices-screen";
import { renderWithQuery } from "@/test/render-query";

it("shows the device tree and loads only locations mapped to the selected controller", async () => {
  const requested: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    requested.push(url);
    const parsed = new URL(url);
    let body: unknown;
    if (parsed.pathname === "/api/v1/gateways") {
      body = [
        {
          id: "gateway-a",
          site_id: "site-1",
          zone_id: "zone-a",
          code: "GW-A",
          name: "Gateway A",
          status: "ONLINE",
          last_seen_at: "2026-08-27T03:00:00Z",
          firmware_version: "sim-1",
          is_simulated: true,
          affected_locations: 300,
        },
      ];
    } else if (parsed.pathname === "/api/v1/controllers") {
      body = [
        {
          id: "controller-a04",
          gateway_id: "gateway-a",
          gateway_code: "GW-A",
          code: "CTRL-A-04",
          address: 4,
          channel_capacity: 64,
          status: "OFFLINE",
          last_seen_at: "2026-08-27T02:59:00Z",
          is_active: true,
          affected_locations: 64,
        },
      ];
    } else {
      body = {
        items: [
          {
            id: "location-a250",
            site_id: "site-1",
            code: "A250",
            zone: { code: "A", name: "Khu A" },
            person: { id: "person-1", full_name: "Người đã khuất A250" },
            hardware: { gateway_code: "GW-A", controller_code: "CTRL-A-04", channel: 58 },
            light: { desired_state: "ON", actual_state: "UNKNOWN", lamp_health: "UNKNOWN" },
            is_active: true,
          },
        ],
        page: 1,
        page_size: 100,
        total: 1,
      };
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  const user = userEvent.setup();
  renderWithQuery(<DevicesScreen />);

  expect(await screen.findByText("GW-A")).toBeInTheDocument();
  const controller = screen.getByRole("button", { name: /CTRL-A-04/ });
  expect(controller).toHaveTextContent("OFFLINE");
  expect(controller).toHaveTextContent("64 vị trí");
  await user.click(controller);

  expect(await screen.findByRole("link", { name: /A250/ })).toHaveTextContent("UNKNOWN");
  expect(requested).toContain(
    "http://localhost:8000/api/v1/locations?controller_id=controller-a04&page=1&page_size=100",
  );
});
