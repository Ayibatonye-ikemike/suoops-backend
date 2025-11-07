"use client";

import { useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { verifySubscription } from "@/api/subscription";

export default function SubscriptionSuccessPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [status, setStatus] = useState<"verifying" | "success" | "error">("verifying");
  const [message, setMessage] = useState("");
  const [planInfo, setPlanInfo] = useState<{ old_plan?: string; new_plan?: string; amount_paid?: number } | null>(null);

  useEffect(() => {
    const reference = searchParams.get("reference");
    
    if (!reference) {
      setStatus("error");
      setMessage("Invalid payment reference. Please contact support.");
      return;
    }

    // Verify payment
    verifySubscription(reference)
      .then((data) => {
        if (data.status === "success") {
          setStatus("success");
          setMessage(data.message || "Payment successful!");
          setPlanInfo({
            old_plan: data.old_plan,
            new_plan: data.new_plan,
            amount_paid: data.amount_paid,
          });
        } else {
          setStatus("error");
          setMessage(data.message || "Payment verification failed");
        }
      })
      .catch((error) => {
        setStatus("error");
        setMessage(error.response?.data?.detail || "Failed to verify payment. Please contact support.");
      });
  }, [searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-md rounded-lg bg-white p-8 shadow-lg">
        {status === "verifying" && (
          <div className="text-center">
            <div className="mx-auto mb-4 h-16 w-16 animate-spin rounded-full border-4 border-blue-600 border-t-transparent"></div>
            <h2 className="text-xl font-bold text-slate-900">Verifying Payment...</h2>
            <p className="mt-2 text-sm text-slate-600">Please wait while we confirm your payment.</p>
          </div>
        )}

        {status === "success" && (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
              <span className="text-4xl">✓</span>
            </div>
            <h2 className="text-xl font-bold text-green-700">Payment Successful!</h2>
            <p className="mt-2 text-sm text-slate-700">{message}</p>

            {planInfo && (
              <div className="mt-4 rounded-lg bg-slate-50 p-4 text-left">
                <p className="text-sm text-slate-600">
                  <strong>Previous Plan:</strong> {planInfo.old_plan}
                </p>
                <p className="text-sm text-slate-600">
                  <strong>New Plan:</strong> <span className="text-green-600">{planInfo.new_plan}</span>
                </p>
                {planInfo.amount_paid && (
                  <p className="text-sm text-slate-600">
                    <strong>Amount Paid:</strong> ₦{planInfo.amount_paid.toLocaleString()}
                  </p>
                )}
              </div>
            )}

            <button
              onClick={() => router.push("/dashboard/settings")}
              className="mt-6 w-full rounded-lg bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700"
            >
              Go to Settings
            </button>
          </div>
        )}

        {status === "error" && (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
              <span className="text-4xl">✗</span>
            </div>
            <h2 className="text-xl font-bold text-red-700">Payment Failed</h2>
            <p className="mt-2 text-sm text-slate-700">{message}</p>

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => router.push("/dashboard/settings")}
                className="flex-1 rounded-lg border border-slate-200 px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Back to Settings
              </button>
              <button
                onClick={() => window.location.reload()}
                className="flex-1 rounded-lg bg-blue-600 px-4 py-3 text-sm font-medium text-white hover:bg-blue-700"
              >
                Retry Verification
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
