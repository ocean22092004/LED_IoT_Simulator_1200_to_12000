import { apiRequest, ApiError } from "./client";
import { setAccessToken } from "@/lib/auth/token-store";

describe("apiRequest", () => {
  it("attaches the session bearer token and returns JSON", async () => {
    setAccessToken("jwt-for-test");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "user-1", username: "admin", role: "ADMIN" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    const result = await apiRequest<{ username: string }>("/api/v1/auth/me");

    expect(result.username).toBe("admin");
    const request = fetchMock.mock.calls[0][1];
    expect(new Headers(request?.headers).get("Authorization")).toBe(
      "Bearer jwt-for-test",
    );
  });

  it("normalizes the public API error and clears an expired token", async () => {
    setAccessToken("expired-token");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "AUTH_INVALID_TOKEN",
            message: "Token expired",
            details: {},
          },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );

    const request = apiRequest("/api/v1/auth/me");
    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      status: 401,
      code: "AUTH_INVALID_TOKEN",
      message: "Token expired",
    });
    expect(window.sessionStorage.getItem("memorial_access_token")).toBeNull();
  });
});
