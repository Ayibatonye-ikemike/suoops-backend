"use client";

import axios from "axios";

import { getConfig } from "@/lib/config";

const { apiBaseUrl } = getConfig();

export type TokenPayload = {
  access_token: string;
  token_type: string;
  access_expires_at: string;
  refresh_token?: string | null;
};

export type MessagePayload = { detail: string };

export type SignupStartPayload = {
  phone?: string | null;
  email?: string | null;
  name: string;
  business_name?: string | null;
};

export type SignupVerifyPayload = {
  phone?: string | null;
  email?: string | null;
  otp: string;
};

export type LoginRequestPayload = { 
  phone?: string | null;
  email?: string | null;
};

export type LoginVerifyPayload = {
  phone?: string | null;
  email?: string | null;
  otp: string;
};

export type OTPResendPayload = {
  phone?: string | null;
  email?: string | null;
  purpose: "signup" | "login";
};

const jsonHeaders = { "Content-Type": "application/json" };

export async function requestSignupOTP(payload: SignupStartPayload): Promise<MessagePayload> {
  const { data } = await axios.post<MessagePayload>(`${apiBaseUrl}/auth/signup/request`, payload, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function verifySignupOTP(payload: SignupVerifyPayload): Promise<TokenPayload> {
  const { data } = await axios.post<TokenPayload>(`${apiBaseUrl}/auth/signup/verify`, payload, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function requestLoginOTP(payload: LoginRequestPayload): Promise<MessagePayload> {
  const { data } = await axios.post<MessagePayload>(`${apiBaseUrl}/auth/login/request`, payload, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function verifyLoginOTP(payload: LoginVerifyPayload): Promise<TokenPayload> {
  const { data } = await axios.post<TokenPayload>(`${apiBaseUrl}/auth/login/verify`, payload, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function resendOTP(payload: OTPResendPayload): Promise<MessagePayload> {
  const { data } = await axios.post<MessagePayload>(`${apiBaseUrl}/auth/otp/resend`, payload, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function refreshSession(): Promise<TokenPayload> {
  const { data } = await axios.post<TokenPayload>(`${apiBaseUrl}/auth/refresh`, {}, {
    headers: jsonHeaders,
    withCredentials: true,
  });
  return data;
}

export async function logout(): Promise<void> {
  await axios.post(`${apiBaseUrl}/auth/logout`, {}, {
    headers: jsonHeaders,
    withCredentials: true,
  });
}
