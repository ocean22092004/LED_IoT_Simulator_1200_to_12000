"use client";

import type { ReactNode } from "react";

import { useAuth } from "@/lib/auth/auth-context";
import { AuthGuard } from "@/lib/auth/auth-guard";
import { RealtimeBridge } from "@/lib/realtime/realtime-bridge";
import { AppShell } from "./app-shell";

function AuthenticatedShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  if (!user) {
    return null;
  }
  return (
    <>
      <RealtimeBridge />
      <AppShell user={user} onLogout={logout}>
        {children}
      </AppShell>
    </>
  );
}

export function ProtectedShell({ children }: { children: ReactNode }) {
  return (
    <AuthGuard>
      <AuthenticatedShell>{children}</AuthenticatedShell>
    </AuthGuard>
  );
}
