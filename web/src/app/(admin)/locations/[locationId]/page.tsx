import { LocationPageClient } from "@/components/location-page-client";

export default async function LocationPage({
  params,
}: {
  params: Promise<{ locationId: string }>;
}) {
  const { locationId } = await params;
  return <LocationPageClient locationId={locationId} />;
}
