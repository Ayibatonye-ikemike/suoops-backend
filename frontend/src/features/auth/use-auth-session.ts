"use client";

import { useCallback } from "react";

import { useAuthStore } from "./auth-store";
import { logout as logoutApi } from "./auth-api";

export function useAuthSession() {
  return useAuthStore((state) => ({
    status: state.status,
    accessToken: state.accessToken,
    accessExpiresAt: state.accessExpiresAt,
  }));
}

export function useLogout() {
  const clearTokens = useAuthStore((state) => state.clearTokens);
  return useCallback(() => {
    void logoutApi().catch((error) => {
      console.error("Failed to revoke session", error);
    });
    clearTokens();
  }, [clearTokens]);
}
