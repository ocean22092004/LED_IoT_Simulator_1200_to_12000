import { render, screen } from "@testing-library/react";
import { useRouter } from "next/navigation";

import { AuthProvider } from "./auth-context";
import { AuthGuard } from "./auth-guard";

vi.mock("next/navigation", () => ({
  useRouter: vi.fn(),
}));

const replace = vi.fn();
const router = {
  bfcacheId: "test",
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  push: vi.fn(),
  replace,
  prefetch: vi.fn(),
};

beforeEach(() => {
  vi.mocked(useRouter).mockReturnValue(router);
});

it("renders protected content after validating the session", async () => {
  window.sessionStorage.setItem("memorial_access_token", "valid-jwt");
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ id: "user-1", username: "staff", role: "STAFF" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );

  render(
    <AuthProvider>
      <AuthGuard>
        <p>Nội dung quản trị</p>
      </AuthGuard>
    </AuthProvider>,
  );

  expect(await screen.findByText("Nội dung quản trị")).toBeInTheDocument();
  expect(replace).not.toHaveBeenCalled();
});

it("redirects an anonymous visitor to login", async () => {
  render(
    <AuthProvider>
      <AuthGuard>
        <p>Nội dung quản trị</p>
      </AuthGuard>
    </AuthProvider>,
  );

  expect(await screen.findByText("Đang chuyển đến đăng nhập…")).toBeInTheDocument();
  expect(replace).toHaveBeenCalledWith("/login");
  expect(screen.queryByText("Nội dung quản trị")).not.toBeInTheDocument();
});
