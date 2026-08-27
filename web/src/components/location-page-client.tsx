"use client";

import { useAuth } from "@/lib/auth/auth-context";
import { LocationDetailScreen } from "./location-detail-screen";

export function LocationPageClient({ locationId }: { locationId: string }) {
  const { user } = useAuth();
  if (!user) {
    return null;
  }
  return <LocationDetailScreen locationId={locationId} role={user.role} />;
}
