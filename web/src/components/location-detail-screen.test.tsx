import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LocationDetailScreen } from "./location-detail-screen";
import type { LocationDetail } from "@/lib/api/domain";
import type { UserRole } from "@/lib/api/types";
import { renderWithQuery } from "@/test/render-query";

const detail: LocationDetail = {
  id: "location-a250",
  site_id: "site-1",
  code: "A250",
  zone: { code: "A", name: "Khu A" },
  person: { id: "person-1", full_name: "Người đã khuất A250" },
  hardware: {
    gateway_code: "GW-A",
    controller_code: "CTRL-A-04",
    channel: 58,
  },
  is_active: true,
  anniversary: { lunar_day: 15, lunar_month: 7, is_leap_month: false },
  light: {
    desired_state: "ON",
    actual_state: "OFF",
    lamp_health: "OK",
    current_ma: "42.50",
    active_reasons: ["ANNIVERSARY", "VISIT"],
    last_reported_at: "2026-08-27T03:00:00Z",
  },
  active_activations: [
    {
      id: "activation-anniversary",
      reason: "ANNIVERSARY",
      starts_at: "2026-08-26T17:00:00Z",
      expires_at: "2026-08-27T16:59:59Z",
    },
    {
      id: "activation-visit",
      reason: "VISIT",
      starts_at: "2026-08-27T02:30:00Z",
      expires_at: "2026-08-27T03:30:00Z",
    },
  ],
  recent_commands: [
    {
      id: "command-1",
      target_state: "ON",
      status: "ACKED",
      reason: "ANNIVERSARY,VISIT",
      attempt_count: 1,
      last_error: null,
      created_at: "2026-08-27T02:30:00Z",
      sent_at: "2026-08-27T02:30:01Z",
      acked_at: "2026-08-27T02:30:02Z",
    },
  ],
  recent_events: [
    {
      id: 1,
      event_type: "TELEMETRY",
      occurred_at: "2026-08-27T03:00:00Z",
      received_at: "2026-08-27T03:00:00Z",
      payload: { current_ma: 42.5 },
    },
  ],
};

function installDetailFetch(value: LocationDetail = detail) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(value), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

it("shows independent desired and actual state with overlapping reasons and history", async () => {
  installDetailFetch();
  renderWithQuery(<LocationDetailScreen locationId="location-a250" role="ADMIN" />);

  expect(await screen.findByRole("heading", { name: "A250" })).toBeInTheDocument();
  expect(screen.getByText("Người đã khuất A250")).toBeInTheDocument();
  expect(screen.getByText("15/7 âm lịch")).toBeInTheDocument();
  expect(screen.getByText("GW-A · CTRL-A-04 · Kênh 58")).toBeInTheDocument();
  expect(screen.getByText("42.50 mA")).toBeInTheDocument();
  expect(screen.getByTestId("desired-state")).toHaveTextContent("ON");
  expect(screen.getByTestId("actual-state")).toHaveTextContent("OFF");
  expect(screen.getByLabelText("Lý do đang hoạt động")).toHaveTextContent(
    "ANNIVERSARYVISIT",
  );
  expect(screen.getByText("ANNIVERSARY,VISIT")).toBeInTheDocument();
  expect(screen.getByText("TELEMETRY")).toBeInTheDocument();
});

it.each<[UserRole, string[], string[]]>([
  ["STAFF", ["Bắt đầu thăm viếng", "Kết thúc thăm viếng"], ["Manual ON", "Manual OFF"]],
  ["TECHNICIAN", ["Manual ON", "Manual OFF"], ["Bắt đầu thăm viếng", "Kết thúc thăm viếng"]],
  ["ADMIN", ["Bắt đầu thăm viếng", "Kết thúc thăm viếng", "Manual ON", "Manual OFF"], []],
])("shows only the actions allowed for %s", async (role, visible, hidden) => {
  installDetailFetch();
  renderWithQuery(<LocationDetailScreen locationId="location-a250" role={role} />);
  await screen.findByRole("heading", { name: "A250" });

  for (const name of visible) {
    expect(screen.getByRole("button", { name })).toBeInTheDocument();
  }
  for (const name of hidden) {
    expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
  }
});

it("refreshes desired after starting a visit without changing actual optimistically", async () => {
  let detailReads = 0;
  const requests: Array<{ url: string; method: string; body: string | null }> = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    requests.push({ url, method, body: typeof init?.body === "string" ? init.body : null });
    if (method === "POST") {
      return new Response(
        JSON.stringify({
          id: "activation-new",
          location_id: "location-a250",
          reason: "VISIT",
          starts_at: "2026-08-27T04:00:00Z",
          expires_at: "2026-08-27T05:00:00Z",
          created_by_user_id: "user-1",
          ended_at: null,
          created_at: "2026-08-27T04:00:00Z",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    }
    detailReads += 1;
    return new Response(
      JSON.stringify({
        ...detail,
        light: {
          ...detail.light,
          desired_state: detailReads > 1 ? "ON" : "OFF",
          actual_state: "OFF",
          active_reasons: detailReads > 1 ? ["ANNIVERSARY", "VISIT"] : ["ANNIVERSARY"],
        },
        active_activations: detail.active_activations.slice(0, detailReads > 1 ? 2 : 1),
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
  const user = userEvent.setup();
  renderWithQuery(<LocationDetailScreen locationId="location-a250" role="STAFF" />);
  expect(await screen.findByTestId("desired-state")).toHaveTextContent("OFF");
  expect(screen.getByTestId("actual-state")).toHaveTextContent("OFF");

  await user.selectOptions(screen.getByLabelText("Thời lượng thăm viếng"), "60");
  await user.click(screen.getByRole("button", { name: "Bắt đầu thăm viếng" }));

  expect(await screen.findByText("Đã bắt đầu thăm viếng")).toBeInTheDocument();
  expect(await screen.findByTestId("desired-state")).toHaveTextContent("ON");
  expect(screen.getByTestId("actual-state")).toHaveTextContent("OFF");
  expect(requests).toContainEqual({
    url: "http://localhost:8000/api/v1/locations/location-a250/visits",
    method: "POST",
    body: JSON.stringify({ duration_minutes: 60 }),
  });
});

it("ends the active Visit by activation id", async () => {
  const fetchMock = installDetailFetch();
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(detail), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  fetchMock.mockResolvedValueOnce(
    new Response(
      JSON.stringify({
        id: "activation-visit",
        location_id: "location-a250",
        reason: "VISIT",
        starts_at: "2026-08-27T02:30:00Z",
        expires_at: "2026-08-27T03:30:00Z",
        created_by_user_id: "user-1",
        ended_at: "2026-08-27T03:00:00Z",
        created_at: "2026-08-27T02:30:00Z",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );
  const user = userEvent.setup();
  renderWithQuery(<LocationDetailScreen locationId="location-a250" role="STAFF" />);
  await screen.findByRole("heading", { name: "A250" });

  await user.click(screen.getByRole("button", { name: "Kết thúc thăm viếng" }));

  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:8000/api/v1/activations/activation-visit/end",
    expect.objectContaining({ method: "POST" }),
  );
});
