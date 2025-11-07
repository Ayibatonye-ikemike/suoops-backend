"use client";

import axios from "axios";

import { getConfig } from "@/lib/config";

const { apiBaseUrl } = getConfig();

export type LoginCredentials = {
  phone: string;
  password: string;
};

export type TokenPayload = {
  access_token: string;
  refresh_token: string;
};

export async function login(credentials: LoginCredentials): Promise<TokenPayload> {
  const { data } = await axios.post<TokenPayload>(`${apiBaseUrl}/auth/login`, credentials, {
    headers: { "Content-Type": "application/json" },
    withCredentials: false,
  });
  return data;
}

export async function refreshSession(refreshToken: string): Promise<TokenPayload> {
  const { data } = await axios.post<TokenPayload>(
    `${apiBaseUrl}/auth/refresh`,
    { refresh_token: refreshToken },
    { headers: { "Content-Type": "application/json" } }
  );
  return data;
}
