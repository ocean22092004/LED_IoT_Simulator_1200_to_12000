"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "./auth-context";

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status } = useAuth();

  useEffect(() => {
    if (status === "anonymous") {
      router.replace("/login");
    }
  }, [router, status]);

  if (status === "loading") {
    return <p role="status">Đang xác thực…</p>;
  }
  if (status === "anonymous") {
    return <p role="status">Đang chuyển đến đăng nhập…</p>;
  }
  return children;
}
