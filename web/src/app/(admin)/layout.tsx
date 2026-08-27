import type { ReactNode } from "react";

import { ProtectedShell } from "@/components/protected-shell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <ProtectedShell>{children}</ProtectedShell>;
}
