"use client";

import axios, {
  AxiosHeaders,
  type AxiosError,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";

import { getConfig } from "@/lib/config";
import { useAuthStore } from "@/features/auth/auth-store";

type RetriableRequestConfig = InternalAxiosRequestConfig & { _retry?: boolean };

const { apiBaseUrl } = getConfig();

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (typeof window === "undefined") {
    return config;
  }
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableRequestConfig | undefined;
    if (
      error.response?.status === 401 &&
      config &&
      !config._retry &&
      typeof window !== "undefined" &&
      !config.url?.startsWith("/auth/")
    ) {
      config._retry = true;
      try {
        const tokens = await useAuthStore.getState().refresh();
        const headers = AxiosHeaders.from(config.headers ?? {});
        headers.set("Authorization", `Bearer ${tokens.accessToken}`);
        config.headers = headers;
        return apiClient(config);
      } catch (refreshError) {
        useAuthStore.getState().markSessionExpired();
        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  }
);
