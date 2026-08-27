"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { useAuth } from "@/lib/auth/auth-context";
import { getAccessToken } from "@/lib/auth/token-store";
import { connectRealtime } from "./client";
import { invalidateForRealtimeEvent } from "./invalidation";

export function RealtimeBridge() {
  const queryClient = useQueryClient();
  const { status } = useAuth();

  useEffect(() => {
    const token = getAccessToken();
    if (status !== "authenticated" || !token) {
      return;
    }
    return connectRealtime(token, (event) => {
      void invalidateForRealtimeEvent(queryClient, event);
    });
  }, [queryClient, status]);
  return null;
}
