/**
 * Phone Number Verification Section
 * 
 * Allows users to add and verify their WhatsApp phone number.
 * Uses OTP verification via WhatsApp Business API.
 * 
 * Design Principles:
 * - SRP: Single responsibility for phone verification UI
 * - DRY: Reuses OTPInput component from auth
 * - OOP: Clean state management with React hooks
 */

"use client";

import { useCallback, useState } from "react";
import { requestPhoneOTP, verifyPhoneOTP, removePhone } from "./phone-api";
import { OTPInput } from "@/features/auth/otp-input";

/**
 * Normalize phone number to E.164 format
 * Handles Nigerian numbers: 0801234567 → +2348012345678
 */
function normalizePhone(input: string): string {
  const trimmed = input.replace(/\s+/g, "");
  if (trimmed.startsWith("+")) return trimmed;
  if (trimmed.startsWith("0")) return `+234${trimmed.slice(1)}`;
  if (trimmed.startsWith("234")) return `+${trimmed}`;
  return `+${trimmed}`;
}

type VerificationStep = "input" | "otp" | "verified";

interface PhoneNumberSectionProps {
  /** Current user phone number (if any) */
  currentPhone?: string | null;
  /** Callback after successful verification */
  onPhoneVerified?: (phone: string) => void;
}

/**
 * Phone Number Section Component
 * 
 * Displays current phone status and handles add/verify/remove flow:
 * 1. No phone → Show input field + "Send OTP" button
 * 2. OTP sent → Show 6-digit input + verify button
 * 3. Verified → Show phone number + "Remove" button
 */
export function PhoneNumberSection({ currentPhone, onPhoneVerified }: PhoneNumberSectionProps) {
  // Component state
  const [step, setStep] = useState<VerificationStep>(currentPhone ? "verified" : "input");
  const [phone, setPhone] = useState(currentPhone || "");
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  /**
   * Handle phone number input and request OTP
   */
  const handleRequestOTP = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    const formData = new FormData(event.currentTarget);
    const phoneInput = formData.get("phone") as string;

    if (!phoneInput?.trim()) {
      setError("Enter your WhatsApp number");
      return;
    }

    setLoading(true);
    const normalizedPhone = normalizePhone(phoneInput);

    try {
      await requestPhoneOTP({ phone: normalizedPhone });
      setPhone(normalizedPhone);
      setStep("otp");
      setOtp("");
      setSuccess("OTP sent to WhatsApp!");
    } catch (err) {
      const message = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Failed to send OTP. Try again.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Handle OTP verification
   */
  const handleVerifyOTP = useCallback(async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    setSuccess(null);

    if (otp.length !== 6) {
      setError("Enter the 6-digit code");
      return;
    }

    setLoading(true);

    try {
      const response = await verifyPhoneOTP({ phone, otp });
      setStep("verified");
      setSuccess(response.detail || "Phone verified successfully!");
      setOtp("");
      onPhoneVerified?.(phone);
    } catch (err) {
      const message = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Invalid code. Try again.";
      setError(message);
      setOtp("");
    } finally {
      setLoading(false);
    }
  }, [otp, phone, onPhoneVerified]);

  /**
   * Handle phone number removal
   */
  const handleRemovePhone = useCallback(async () => {
    if (!confirm("Remove phone number from your account?")) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      await removePhone();
      setPhone("");
      setStep("input");
      setSuccess("Phone number removed");
    } catch (err) {
      const message = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || "Failed to remove phone number";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  /**
   * Reset to input step
   */
  const handleBackToInput = useCallback(() => {
    setStep("input");
    setOtp("");
    setError(null);
    setSuccess(null);
  }, []);

  // Render verified state
  if (step === "verified") {
    return (
      <div className="space-y-4">
        {success && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {success}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <div>
            <p className="text-sm font-medium text-slate-700">WhatsApp Number</p>
            <p className="mt-1 text-base font-semibold text-slate-900">{phone}</p>
            <p className="mt-1 text-xs text-emerald-600">✓ Verified</p>
          </div>
          <button
            type="button"
            onClick={handleRemovePhone}
            disabled={loading}
            className="rounded-lg border border-rose-200 bg-white px-4 py-2 text-sm font-medium text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Removing..." : "Remove"}
          </button>
        </div>
        <p className="text-xs text-slate-500">
          You can now use this number to login and receive invoice notifications via WhatsApp.
        </p>
      </div>
    );
  }

  // Render OTP verification step
  if (step === "otp") {
    return (
      <form onSubmit={handleVerifyOTP} className="space-y-4">
        {success && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {success}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
            {error}
          </div>
        )}
        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-700">
            Enter 6-digit code sent to {phone}
          </label>
          <OTPInput
            value={otp}
            onChange={setOtp}
            disabled={loading}
            hasError={Boolean(error)}
          />
        </div>
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={loading || otp.length !== 6}
            className="flex-1 rounded-lg bg-brand-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? "Verifying..." : "Verify Number"}
          </button>
          <button
            type="button"
            onClick={handleBackToInput}
            disabled={loading}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Back
          </button>
        </div>
      </form>
    );
  }

  // Render phone input step
  return (
    <form onSubmit={handleRequestOTP} className="space-y-4">
      {success && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {success}
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
          {error}
        </div>
      )}
      <div className="space-y-2">
        <label htmlFor="phone" className="text-sm font-medium text-slate-700">
          WhatsApp Number
        </label>
        <input
          id="phone"
          name="phone"
          type="tel"
          defaultValue={phone}
          placeholder="0801 234 5678"
          required
          disabled={loading}
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:cursor-not-allowed disabled:bg-slate-50"
        />
        <p className="text-xs text-slate-500">
          We&apos;ll send a verification code to this WhatsApp number
        </p>
      </div>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-brand-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Sending..." : "Send Verification Code"}
      </button>
    </form>
  );
}
