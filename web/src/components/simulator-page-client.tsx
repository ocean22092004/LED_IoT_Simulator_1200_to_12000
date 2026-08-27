"use client";

import { useAuth } from "@/lib/auth/auth-context";
import { SimulatorScreen } from "./simulator-screen";

export function SimulatorPageClient() {
  const { user } = useAuth();
  if (!user) {
    return null;
  }
  return <SimulatorScreen role={user.role} />;
}
