/**
 * Phone Verification API Client
 * 
 * Handles phone number addition and verification for user accounts.
 * Uses WhatsApp OTP for verification when Meta approves the app.
 */

import { apiClient } from "@/api/client";

/**
 * Request to add/update phone number
 */
export interface AddPhoneRequest {
  phone: string;
}

/**
 * Request to verify phone with OTP
 */
export interface VerifyPhoneRequest {
  phone: string;
  otp: string;
}

/**
 * Response after successful phone verification
 */
export interface PhoneVerificationResponse {
  detail: string;
  phone: string;
}

/**
 * Request OTP to be sent to phone number
 * 
 * @param request - Phone number to verify
 * @returns Promise with success message
 */
export async function requestPhoneOTP(request: AddPhoneRequest): Promise<{ detail: string }> {
  const response = await apiClient.post<{ detail: string }>("/user/phone/request", request);
  return response.data;
}

/**
 * Verify phone number with OTP code
 * 
 * @param request - Phone number and OTP code
 * @returns Promise with verification result
 */
export async function verifyPhoneOTP(request: VerifyPhoneRequest): Promise<PhoneVerificationResponse> {
  const response = await apiClient.post<PhoneVerificationResponse>("/user/phone/verify", request);
  return response.data;
}

/**
 * Remove phone number from account
 * 
 * @returns Promise with success message
 */
export async function removePhone(): Promise<{ detail: string }> {
  const response = await apiClient.delete<{ detail: string }>("/user/phone");
  return response.data;
}
