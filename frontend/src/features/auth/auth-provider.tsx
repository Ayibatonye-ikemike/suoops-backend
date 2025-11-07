"use client";

import { useEffect, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { initializeAuth } from "./auth-store";

let bootstrapped = false;

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  useEffect(() => {
    // Skip bootstrapping while we're on the OAuth callback route to prevent
    // an early refresh attempt before the callback exchange sets the cookies.
    if (pathname?.startsWith("/auth/callback")) {
      return;
    }
    if (!bootstrapped) {
      bootstrapped = true;
      void initializeAuth();
    }
  }, [pathname]);

  return <>{children}</>;
}
