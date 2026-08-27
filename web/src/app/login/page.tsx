"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/auth-context";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setMessage(null);
    try {
      await login(username.trim(), password);
      setMessage("Đăng nhập thành công");
      router.replace("/");
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.code === "AUTH_INVALID_CREDENTIALS"
          ? "Tên đăng nhập hoặc mật khẩu không đúng"
          : "Không thể đăng nhập. Vui lòng thử lại.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-5 py-10">
      <section className="grid w-full max-w-5xl overflow-hidden rounded-[2rem] border border-[var(--line)] bg-[var(--surface)] shadow-2xl shadow-stone-900/10 md:grid-cols-[1.1fr_0.9fr]">
        <div className="hidden bg-[var(--pine-dark)] p-12 text-stone-50 md:flex md:flex-col md:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.28em] text-amber-300">
              Memorial IoT
            </p>
            <h1 className="mt-6 text-5xl font-semibold leading-tight">
              Điều hành ánh sáng với sự an tâm.
            </h1>
          </div>
          <p className="max-w-sm text-sm leading-6 text-stone-300">
            Theo dõi riêng biệt trạng thái yêu cầu và trạng thái thực tế của từng vị trí.
          </p>
        </div>
        <div className="p-7 sm:p-12">
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-[var(--pine)]">
            Khu quản trị
          </p>
          <h2 className="mt-3 text-3xl font-semibold">Đăng nhập</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">
            Dùng tài khoản được cấp để tiếp tục.
          </p>
          <form className="mt-9 space-y-5" onSubmit={submit}>
            <label className="block text-sm font-semibold">
              Tên đăng nhập
              <input
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3 outline-none transition focus:border-[var(--pine)] focus:ring-4 focus:ring-emerald-900/10"
                autoComplete="username"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-semibold">
              Mật khẩu
              <input
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-white px-4 py-3 outline-none transition focus:border-[var(--pine)] focus:ring-4 focus:ring-emerald-900/10"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            {message ? (
              <p
                className="rounded-xl bg-stone-100 px-4 py-3 text-sm"
                role={message === "Đăng nhập thành công" ? "status" : "alert"}
              >
                {message}
              </p>
            ) : null}
            <button
              className="w-full rounded-xl bg-[var(--pine)] px-5 py-3 font-semibold text-white transition hover:bg-[var(--pine-dark)] disabled:opacity-60"
              disabled={pending}
              type="submit"
            >
              {pending ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
