"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function PaymentConfirmContent() {
  const searchParams = useSearchParams();
  const reference = searchParams.get("reference");
  const status = searchParams.get("status");
  const trxref = searchParams.get("trxref");

  // Paystack returns: ?reference=INV-xxx&trxref=xxx&status=success
  const isSuccess = status === "success";
  const isCancelled = status === "cancelled";

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-8 shadow-lg">
        {isSuccess ? (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
              <svg
                className="h-8 w-8 text-emerald-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </div>
            <h1 className="mb-2 text-2xl font-bold text-slate-900">Payment Successful! 🎉</h1>
            <p className="mb-6 text-slate-600">
              Your payment has been processed successfully. The invoice will be updated shortly.
            </p>
            {reference ? (
              <div className="mb-6 rounded-lg bg-slate-50 p-4 text-left">
                <p className="text-sm font-semibold text-slate-700">Invoice Reference</p>
                <p className="font-mono text-sm text-slate-900">{reference}</p>
                {trxref ? (
                  <>
                    <p className="mt-2 text-sm font-semibold text-slate-700">Transaction ID</p>
                    <p className="font-mono text-sm text-slate-900">{trxref}</p>
                  </>
                ) : null}
              </div>
            ) : null}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Link
                href="/dashboard"
                className="rounded-lg bg-brand-primary px-6 py-3 text-center font-semibold text-white transition hover:bg-brand-primary/90"
              >
                View Invoices
              </Link>
              <Link
                href="/"
                className="rounded-lg border border-slate-300 bg-white px-6 py-3 text-center font-semibold text-slate-700 transition hover:bg-slate-50"
              >
                Go Home
              </Link>
            </div>
          </div>
        ) : isCancelled ? (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-amber-100">
              <svg
                className="h-8 w-8 text-amber-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h1 className="mb-2 text-2xl font-bold text-slate-900">Payment Cancelled</h1>
            <p className="mb-6 text-slate-600">
              The payment was cancelled. You can try again or contact support if you need help.
            </p>
            {reference ? (
              <div className="mb-6 rounded-lg bg-slate-50 p-4 text-left">
                <p className="text-sm font-semibold text-slate-700">Invoice Reference</p>
                <p className="font-mono text-sm text-slate-900">{reference}</p>
              </div>
            ) : null}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Link
                href="/dashboard"
                className="rounded-lg bg-brand-primary px-6 py-3 text-center font-semibold text-white transition hover:bg-brand-primary/90"
              >
                Back to Invoices
              </Link>
            </div>
          </div>
        ) : (
          <div className="text-center">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-slate-100">
              <svg
                className="h-8 w-8 text-slate-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <h1 className="mb-2 text-2xl font-bold text-slate-900">Payment Status Unknown</h1>
            <p className="mb-6 text-slate-600">
              We couldn&apos;t verify the payment status. Please check your invoices or contact support.
            </p>
            {reference ? (
              <div className="mb-6 rounded-lg bg-slate-50 p-4 text-left">
                <p className="text-sm font-semibold text-slate-700">Invoice Reference</p>
                <p className="font-mono text-sm text-slate-900">{reference}</p>
              </div>
            ) : null}
            <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
              <Link
                href="/dashboard"
                className="rounded-lg bg-brand-primary px-6 py-3 text-center font-semibold text-white transition hover:bg-brand-primary/90"
              >
                View Invoices
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PaymentConfirmPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50">
          <p className="text-slate-600">Loading payment status...</p>
        </div>
      }
    >
      <PaymentConfirmContent />
    </Suspense>
  );
}
