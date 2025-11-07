"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import {
  requestSignupOTP,
  verifySignupOTP,
  resendOTP,
  type SignupStartPayload,
} from "./auth-api";
import { useAuthStore } from "./auth-store";
import { OTPInput } from "./otp-input";

type Step = "details" | "otp";

function normalizePhone(input: string): string {
  const trimmed = input.replace(/\s+/g, "");
  if (trimmed.startsWith("+")) {
    return trimmed;
  }
  if (trimmed.startsWith("0")) {
    return `+234${trimmed.slice(1)}`;
  }
  if (trimmed.startsWith("234")) {
    return `+${trimmed}`;
  }
  return `+${trimmed}`;
}

export function RegisterForm() {
  const router = useRouter();
  const setTokens = useAuthStore((state) => state.setTokens);
  const [step, setStep] = useState<Step>("details");
  const [formValues, setFormValues] = useState<SignupStartPayload | null>(null);
  const [otp, setOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendTimer, setResendTimer] = useState(0);

  const canResend = useMemo(() => resendTimer === 0, [resendTimer]);

  const startResendCountdown = useCallback(() => {
    setResendTimer(60);
    const interval = window.setInterval(() => {
      setResendTimer((prev) => {
        if (prev <= 1) {
          window.clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  const handleRequestOTP = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      const payload: SignupStartPayload = {
        name: String(form.get("name") ?? "").trim(),
        email: String(form.get("email") ?? "").trim().toLowerCase(),
      };
      const businessName = String(form.get("business-name") ?? "").trim();
      if (businessName) {
        payload.business_name = businessName;
      }
      if (!payload.name || !payload.email) {
        setError("Please provide your name and email address.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        await requestSignupOTP(payload);
        setFormValues(payload);
        setStep("otp");
        setOtp("");
        startResendCountdown();
      } catch (requestError: unknown) {
        console.error(requestError);
        const message =
          typeof requestError === "object" && requestError !== null && "response" in requestError
            ? (requestError as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        setError(message || "Unable to send verification code. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [startResendCountdown]
  );

  const handleVerifyOTP = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!formValues) {
        setError("Session expired. Please restart signup.");
        setStep("details");
        return;
      }
      if (otp.length !== 6) {
        setError("Enter the 6-digit code sent to your email.");
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const token = await verifySignupOTP({ email: formValues.email, otp });
        setTokens({ accessToken: token.access_token, accessExpiresAt: token.access_expires_at });
        router.replace("/dashboard");
      } catch (verifyError: unknown) {
        console.error(verifyError);
        setOtp("");
        const message =
          typeof verifyError === "object" && verifyError !== null && "response" in verifyError
            ? (verifyError as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : undefined;
        setError(message || "Invalid code. Please try again.");
      } finally {
        setLoading(false);
      }
    },
    [formValues, otp, router, setTokens]
  );

  const handleResend = useCallback(async () => {
    if (!formValues || !canResend) {
      return;
    }
    try {
      setLoading(true);
      setError(null);
      await resendOTP({ email: formValues.email, purpose: "signup" });
      setOtp("");
      startResendCountdown();
    } catch (resendError: unknown) {
      console.error(resendError);
      const message =
        typeof resendError === "object" && resendError !== null && "response" in resendError
          ? (resendError as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
      setError(message || "Please wait before requesting another code.");
    } finally {
      setLoading(false);
    }
  }, [canResend, formValues, startResendCountdown]);

  if (step === "otp") {
    return (
      <form className="flex w-full max-w-md flex-col gap-6 rounded-2xl bg-white p-10 shadow-xl" onSubmit={handleVerifyOTP}>
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">Verify your email</h1>
          <p className="text-sm text-slate-500">
            Enter the verification code sent to <span className="font-semibold text-slate-700">{formValues?.email}</span>
          </p>
        </div>
        {error ? (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-col items-center gap-4">
          <OTPInput value={otp} onChange={setOtp} disabled={loading} hasError={Boolean(error)} />
          <button
            type="submit"
            disabled={loading || otp.length !== 6}
            className="w-full rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-70"
          >
            {loading ? "Verifying..." : "Verify & Continue"}
          </button>
          <button
            type="button"
            onClick={handleResend}
            disabled={!canResend || loading}
            className="text-sm font-medium text-green-600 hover:text-green-700 hover:underline disabled:cursor-not-allowed disabled:text-slate-400"
          >
            {canResend ? "Resend code" : `Resend available in ${resendTimer}s`}
          </button>
          <button
            type="button"
            onClick={() => {
              setStep("details");
              setError(null);
              setOtp("");
            }}
            className="text-sm text-slate-500 hover:text-slate-700"
          >
            Use a different email
          </button>
        </div>
      </form>
    );
  }

  return (
    <form className="flex w-full max-w-md flex-col gap-6 rounded-2xl bg-white p-10 shadow-xl" onSubmit={handleRequestOTP}>
      <div className="space-y-2 text-center">
        <h1 className="text-2xl font-semibold text-slate-900">Create account</h1>
        <p className="text-sm text-slate-500">We will send an OTP to your email to verify your account.</p>
      </div>
      {error ? (
        <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600" role="alert">
          {error}
        </p>
      ) : null}
      <label className="flex flex-col gap-2 text-left text-sm font-semibold text-slate-700">
        Full name
        <input
          name="name"
          placeholder="Jane Doe"
          required
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-green-600 focus:ring-2 focus:ring-green-600/20"
        />
      </label>
      <label className="flex flex-col gap-2 text-left text-sm font-semibold text-slate-700">
        Email address
        <input
          name="email"
          type="email"
          placeholder="you@example.com"
          required
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-green-600 focus:ring-2 focus:ring-green-600/20"
        />
      </label>
      <label className="flex flex-col gap-2 text-left text-sm font-semibold text-slate-700">
        Business name <span className="text-xs font-normal text-slate-400">Optional</span>
        <input
          name="business-name"
          placeholder="Acme Studios"
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-green-600 focus:ring-2 focus:ring-green-600/20"
        />
      </label>
      <button
        type="submit"
        disabled={loading}
        className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-70"
      >
        {loading ? "Sending code..." : "Send verification code"}
      </button>
      <p className="text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-green-600 hover:text-green-700 hover:underline">
          Sign in
        </Link>
      </p>
    </form>
  );
}
