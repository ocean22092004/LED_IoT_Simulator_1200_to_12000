import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ZoneGridScreen } from "./zone-grid-screen";
import { renderWithQuery } from "@/test/render-query";

it("renders a paginated zone grid with distinct actual and fault states", async () => {
  const requested: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    requested.push(url);
    const parsed = new URL(url);
    if (parsed.pathname === "/api/v1/zones") {
      return new Response(
        JSON.stringify([
          {
            id: "zone-a",
            site_id: "site-1",
            code: "A",
            name: "Khu A",
            sort_order: 1,
            is_active: true,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(
      JSON.stringify({
        items: [
          {
            id: "location-on",
            site_id: "site-1",
            code: "A001",
            zone: { code: "A", name: "Khu A" },
            person: null,
            hardware: { gateway_code: "GW-A", controller_code: "CTRL-A-01", channel: 1 },
            light: { desired_state: "ON", actual_state: "ON", lamp_health: "OK" },
            is_active: true,
          },
          {
            id: "location-off",
            site_id: "site-1",
            code: "A002",
            zone: { code: "A", name: "Khu A" },
            person: null,
            hardware: { gateway_code: "GW-A", controller_code: "CTRL-A-01", channel: 2 },
            light: { desired_state: "OFF", actual_state: "OFF", lamp_health: "OK" },
            is_active: true,
          },
          {
            id: "location-unknown",
            site_id: "site-1",
            code: "A003",
            zone: { code: "A", name: "Khu A" },
            person: null,
            hardware: { gateway_code: "GW-A", controller_code: "CTRL-A-01", channel: 3 },
            light: {
              desired_state: "ON",
              actual_state: "UNKNOWN",
              lamp_health: "SUSPECTED_FAILED",
            },
            is_active: true,
          },
        ],
        page: Number(parsed.searchParams.get("page")),
        page_size: 100,
        total: 300,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
  const user = userEvent.setup();
  renderWithQuery(<ZoneGridScreen />);

  expect(await screen.findByRole("link", { name: /A001/ })).toHaveTextContent("ON");
  expect(screen.getByRole("link", { name: /A002/ })).toHaveTextContent("OFF");
  expect(screen.getByRole("link", { name: /A003/ })).toHaveTextContent("UNKNOWN");
  expect(screen.getByRole("link", { name: /A003/ })).toHaveTextContent("Nghi hỏng");
  expect(requested).toContain(
    "http://localhost:8000/api/v1/zones/zone-a/locations?page=1&page_size=100",
  );

  await user.click(screen.getByRole("button", { name: "Trang sau" }));
  expect(requested).toContain(
    "http://localhost:8000/api/v1/zones/zone-a/locations?page=2&page_size=100",
  );
  expect(screen.getByText("Trang 2 / 3")).toBeInTheDocument();
});
