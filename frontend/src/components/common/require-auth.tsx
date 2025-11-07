"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuthStore } from "@/features/auth/auth-store";

export function RequireAuth({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const status = useAuthStore((state) => state.status);

  useEffect(() => {
    if (status === "unauthenticated") {
      const search = pathname ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${search}`);
    }
    if (status === "expired") {
      const params = new URLSearchParams();
      params.set("reason", "expired");
      if (pathname) {
        params.set("next", pathname);
      }
      router.replace(`/login?${params.toString()}`);
    }
  }, [pathname, router, status]);

  if (status === "idle" || status === "loading") {
    return <p>Verifying session…</p>;
  }

  if (status !== "authenticated") {
    return null;
  }

  return <>{children}</>;
}
