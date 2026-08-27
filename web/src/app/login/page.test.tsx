import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRouter } from "next/navigation";

import LoginPage from "./page";
import { AuthProvider } from "@/lib/auth/auth-context";

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

it("logs in, loads the current user, and enters the dashboard", async () => {
  vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ access_token: "valid-jwt", token_type: "bearer" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ id: "user-1", username: "admin", role: "ADMIN" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
  const user = userEvent.setup();
  render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
  );

  await user.type(screen.getByLabelText("Tên đăng nhập"), "admin");
  await user.type(screen.getByLabelText("Mật khẩu"), "secret");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

  expect(await screen.findByText("Đăng nhập thành công")).toBeInTheDocument();
  expect(window.sessionStorage.getItem("memorial_access_token")).toBe("valid-jwt");
  expect(replace).toHaveBeenCalledWith("/");
});

it("shows the backend login error without exposing the password", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({
        error: {
          code: "AUTH_INVALID_CREDENTIALS",
          message: "Invalid username or password",
          details: {},
        },
      }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    ),
  );
  const user = userEvent.setup();
  render(
    <AuthProvider>
      <LoginPage />
    </AuthProvider>,
  );

  await user.type(screen.getByLabelText("Tên đăng nhập"), "admin");
  await user.type(screen.getByLabelText("Mật khẩu"), "do-not-render-me");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Tên đăng nhập hoặc mật khẩu không đúng",
  );
  expect(screen.queryByText("do-not-render-me")).not.toBeInTheDocument();
});
