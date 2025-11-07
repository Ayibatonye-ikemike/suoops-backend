"use client";

import { create } from "zustand";
import type { AxiosError } from "axios";

import { refreshSession, type TokenPayload } from "./auth-api";

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated" | "expired";

export type SessionTokens = {
  accessToken: string;
  accessExpiresAt: string;
};

type AuthState = {
  accessToken: string | null;
  accessExpiresAt: string | null;
  status: AuthStatus;
  setTokens: (tokens: SessionTokens) => void;
  clearTokens: () => void;
  markSessionExpired: () => void;
  refresh: (options?: { markLoading?: boolean }) => Promise<SessionTokens>;
};

let refreshInFlight: Promise<SessionTokens> | null = null;

export const useAuthStore = create<AuthState>()((set) => ({
  accessToken: null,
  accessExpiresAt: null,
  status: "idle",
  setTokens: ({ accessToken, accessExpiresAt }) =>
    set({ accessToken, accessExpiresAt, status: "authenticated" }),
  clearTokens: () => set({ accessToken: null, accessExpiresAt: null, status: "unauthenticated" }),
  markSessionExpired: () => set({ accessToken: null, accessExpiresAt: null, status: "expired" }),
  refresh: async ({ markLoading } = {}) => {
    if (refreshInFlight) {
      return refreshInFlight;
    }
    if (markLoading) {
      set({ status: "loading" });
    }
    refreshInFlight = refreshSession()
      .then(({ access_token, access_expires_at }: TokenPayload) => {
        const tokens: SessionTokens = {
          accessToken: access_token,
          accessExpiresAt: access_expires_at,
        };
        set({ accessToken: tokens.accessToken, accessExpiresAt: tokens.accessExpiresAt, status: "authenticated" });
        return tokens;
      })
      .catch((error: unknown) => {
        const axiosError = error as AxiosError<{ detail?: string }>;
        const detail = axiosError.response?.data?.detail;
        if (detail === "Missing refresh token") {
          set({ accessToken: null, accessExpiresAt: null, status: "unauthenticated" });
        } else {
          set({ accessToken: null, accessExpiresAt: null, status: "expired" });
        }
        throw error;
      })
      .finally(() => {
        refreshInFlight = null;
      });

    return refreshInFlight;
  },
}));

let initPromise: Promise<void> | null = null;

export function initializeAuth(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.resolve();
  }
  if (initPromise) {
    return initPromise;
  }
  initPromise = (async () => {
    const { refresh, clearTokens } = useAuthStore.getState();
    try {
      await refresh({ markLoading: true });
    } catch (error) {
      console.info("No active session", error);
      const { status } = useAuthStore.getState();
      if (status !== "expired") {
        clearTokens();
      }
    }
  })().finally(() => {
    initPromise = null;
  });

  return initPromise;
}
