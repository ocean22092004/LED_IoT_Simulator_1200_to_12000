import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";

import { AppShell } from "./app-shell";
import { renderWithQuery } from "@/test/render-query";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(),
}));

const push = vi.fn();
const router = {
  bfcacheId: "test",
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  push,
  replace: vi.fn(),
  prefetch: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useRouter).mockReturnValue(router);
});

it("searches A250 and opens a result with its actual state", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        items: [
          {
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
            light: {
              desired_state: "ON",
              actual_state: "UNKNOWN",
              lamp_health: "UNKNOWN",
            },
            is_active: true,
          },
        ],
        page: 1,
        page_size: 8,
        total: 1,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    ),
  );
  const user = userEvent.setup();
  renderWithQuery(
    <AppShell
      user={{ id: "user-1", username: "admin", role: "ADMIN" }}
      onLogout={vi.fn()}
    >
      <p>Nội dung</p>
    </AppShell>,
  );

  await user.type(screen.getByLabelText("Tìm vị trí hoặc tên người"), "A250");

  const result = await screen.findByRole("button", { name: /A250/ });
  expect(result).toHaveTextContent("Người đã khuất A250");
  expect(result).toHaveTextContent("Khu A");
  expect(result).toHaveTextContent("UNKNOWN");
  await user.click(result);
  expect(push).toHaveBeenCalledWith("/locations/location-a250");
});

it("shows the complete navigation and current role", () => {
  renderWithQuery(
    <AppShell
      user={{ id: "user-1", username: "staff", role: "STAFF" }}
      onLogout={vi.fn()}
    >
      <p>Nội dung</p>
    </AppShell>,
  );

  expect(screen.getByRole("navigation", { name: "Điều hướng chính" })).toHaveTextContent(
    "Tổng quanKhu vựcThiết bị",
  );
  expect(screen.getByText("STAFF")).toBeInTheDocument();
  expect(screen.queryByText("Simulator Lab")).not.toBeInTheDocument();
});
