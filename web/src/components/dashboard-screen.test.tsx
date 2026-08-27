import { screen, within } from "@testing-library/react";

import { DashboardScreen } from "./dashboard-screen";
import { renderWithQuery } from "@/test/render-query";

const responses: Record<string, unknown> = {
  "/api/v1/dashboard/summary": {
    total_locations: 1200,
    desired_on: 26,
    actual_on: 25,
    actual_unknown: 64,
    anniversaries_today: 18,
    active_visits: 8,
    gateways_online: 3,
    gateways_offline: 1,
    controllers_online: 19,
    controllers_offline: 1,
    suspected_failed_lamps: 1,
  },
  "/api/v1/dashboard/anniversaries-today": {
    local_date: "2026-08-27",
    total: 1,
    items: [
      {
        activation_id: "activation-1",
        location_id: "location-a250",
        location_code: "A250",
        person_id: "person-1",
        person_name: "Người đã khuất A250",
        zone_code: "A",
        starts_at: "2026-08-26T17:00:00Z",
        expires_at: "2026-08-27T16:59:59Z",
      },
    ],
  },
  "/api/v1/dashboard/device-health": {
    gateways: [
      {
        id: "gateway-1",
        code: "GW-A",
        name: "Gateway A",
        status: "OFFLINE",
        last_seen_at: "2026-08-27T02:00:00Z",
        affected_locations: 300,
      },
    ],
    controllers: [
      {
        id: "controller-1",
        gateway_id: "gateway-1",
        gateway_code: "GW-A",
        code: "CTRL-A-04",
        address: 4,
        status: "OFFLINE",
        last_seen_at: "2026-08-27T02:00:00Z",
        affected_locations: 64,
      },
    ],
  },
  "/api/v1/commands?status=FAILED&page=1&page_size=10": {
    items: [
      {
        id: "command-1",
        location_id: "location-a250",
        location_code: "A250",
        gateway_id: "gateway-1",
        gateway_code: "GW-A",
        controller_id: "controller-1",
        controller_code: "CTRL-A-04",
        channel_number: 58,
        target_state: "ON",
        status: "FAILED",
        reason: "VISIT",
        attempt_count: 3,
        next_attempt_at: "2026-08-27T02:00:00Z",
        sent_at: null,
        acked_at: null,
        last_error: "ACK timeout",
        created_at: "2026-08-27T02:00:00Z",
      },
    ],
    page: 1,
    page_size: 10,
    total: 1,
  },
};

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = new URL(String(input)).pathname + new URL(String(input)).search;
    const body = responses[path];
    if (!body) {
      return new Response("Not found", { status: 404 });
    }
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
});

it("shows all required dashboard cards and today's anniversaries", async () => {
  renderWithQuery(<DashboardScreen />);

  for (const label of [
    "Tổng vị trí",
    "Đang yêu cầu sáng",
    "Actual ON",
    "Unknown",
    "Giỗ hôm nay",
    "Đang thăm viếng",
    "Gateway Offline",
    "Controller Offline",
    "Nghi bóng hỏng",
  ]) {
    expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
  }
  expect(screen.getByRole("link", { name: /A250/ })).toHaveTextContent(
    "Người đã khuất A250",
  );
});

it("orders operational warnings by the specification priority", async () => {
  renderWithQuery(<DashboardScreen />);

  const warningList = await screen.findByRole("list", { name: "Cảnh báo ưu tiên" });
  const items = within(warningList).getAllByRole("listitem");
  expect(items).toHaveLength(4);
  expect(items[0]).toHaveTextContent("GW-A");
  expect(items[1]).toHaveTextContent("CTRL-A-04");
  expect(items[2]).toHaveTextContent("Lệnh A250 thất bại");
  expect(items[3]).toHaveTextContent("1 bóng nghi hỏng");
});
