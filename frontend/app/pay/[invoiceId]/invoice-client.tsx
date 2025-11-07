"use client";

import { useCallback, useMemo, useState } from "react";

import type { components } from "@/api/types";

type InvoicePublic = components["schemas"]["InvoicePublicOut"];

type Props = {
  initialInvoice: InvoicePublic;
  invoiceId: string;
  apiBaseUrl: string;
};

const currencyFormatter = new Intl.NumberFormat("en-NG", {
  style: "currency",
  currency: "NGN",
  minimumFractionDigits: 2,
});

const formatAccountNumber = (value: string | null | undefined) => {
  if (!value) return "";
  return value.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
};

const formatCurrency = (value: string | null | undefined) => {
  if (!value) return "—";
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return currencyFormatter.format(amount);
};

const statusBadgeStyles: Record<string, string> = {
  pending: "bg-amber-50 text-amber-700 border border-amber-200",
  awaiting_confirmation: "bg-amber-100 text-amber-800 border border-amber-200",
  paid: "bg-emerald-50 text-emerald-700 border border-emerald-200",
  failed: "bg-rose-50 text-rose-700 border border-rose-200",
};

export function InvoiceClient({ initialInvoice, invoiceId, apiBaseUrl }: Props) {
  const [invoice, setInvoice] = useState<InvoicePublic>(initialInvoice);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [copyField, setCopyField] = useState<"account" | "name" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isPaid = invoice.status === "paid";
  const isAwaiting = invoice.status === "awaiting_confirmation";
  const isClosed = invoice.status === "failed";

  const paymentMessage = useMemo(() => {
    if (isPaid) {
      return "Thanks! The business has marked this invoice as paid.";
    }
    if (isAwaiting) {
      return "Thanks! The business has been notified. They will confirm once the transfer lands.";
    }
    if (isClosed) {
      return "This invoice is closed. Reach out to the business if you need a fresh invoice.";
    }
    return "Kindly make a bank transfer using the details below. Tap the button once you’ve sent it.";
  }, [isPaid, isAwaiting, isClosed]);

  const handleConfirmTransfer = useCallback(async () => {
    if (isSubmitting || isPaid || isAwaiting || isClosed) {
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setFeedback(null);

    try {
      const response = await fetch(`${apiBaseUrl}/public/invoices/${invoiceId}/confirm-transfer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error("Unable to update invoice right now. Please try again later.");
      }

      const data = (await response.json()) as InvoicePublic;
      setInvoice(data);
      setFeedback("Thanks! We’ve alerted the business to confirm your transfer.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong. Please retry.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  }, [apiBaseUrl, invoiceId, isAwaiting, isClosed, isPaid, isSubmitting]);

  const copyToClipboard = useCallback(
    async (value: string, field: "account" | "name") => {
      if (!value || typeof navigator === "undefined" || !navigator.clipboard) {
        return;
      }
      try {
        await navigator.clipboard.writeText(value);
        setCopyField(field);
        setTimeout(() => setCopyField(null), 2000);
      } catch (copyError) {
        console.error("Failed to copy detail", copyError);
      }
    },
    [],
  );

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col gap-6 px-4 py-10">
      <header className="space-y-3 text-center">
        <p className="text-sm font-medium text-slate-500">Invoice {invoice.invoice_id}</p>
        <h1 className="text-3xl font-semibold text-slate-900">Transfer Payment Instructions</h1>
        <p className="text-sm text-slate-600">{paymentMessage}</p>
      </header>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xl font-semibold text-slate-900">{formatCurrency(invoice.amount)}</p>
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
              statusBadgeStyles[invoice.status] ?? "bg-slate-100 text-slate-700 border border-slate-200"
            }`}
          >
            {invoice.status.replace(/_/g, " ")}
          </span>
        </div>
        {invoice.due_date ? (
          <p className="mt-2 text-xs text-slate-500">
            Due {new Date(invoice.due_date).toLocaleString(undefined, { dateStyle: "medium" })}
          </p>
        ) : null}
      </section>

      <section className="rounded-2xl border border-brand-primary/40 bg-brand-primary/5 p-6">
        <h2 className="text-sm font-semibold text-slate-900">Transfer to</h2>
        <dl className="mt-4 space-y-3 text-sm text-slate-800">
          {invoice.business_name ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Business</dt>
              <dd className="font-medium">{invoice.business_name}</dd>
            </div>
          ) : null}
          {invoice.bank_name ? (
            <div>
              <dt className="text-xs uppercase tracking-wide text-slate-500">Bank</dt>
              <dd className="font-medium">{invoice.bank_name}</dd>
            </div>
          ) : null}
          {invoice.account_number ? (
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex-1">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Account number</dt>
                <dd className="font-mono text-base tracking-[0.2em]">
                  {formatAccountNumber(invoice.account_number)}
                </dd>
              </div>
              <button
                type="button"
                onClick={() => copyToClipboard(invoice.account_number ?? "", "account")}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
              >
                {copyField === "account" ? "Copied!" : "Copy"}
              </button>
            </div>
          ) : null}
          {invoice.account_name ? (
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex-1">
                <dt className="text-xs uppercase tracking-wide text-slate-500">Account name</dt>
                <dd className="font-medium">{invoice.account_name}</dd>
              </div>
              <button
                type="button"
                onClick={() => copyToClipboard(invoice.account_name ?? "", "name")}
                className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-slate-400 hover:text-slate-900"
              >
                {copyField === "name" ? "Copied!" : "Copy"}
              </button>
            </div>
          ) : null}
        </dl>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      {feedback ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
          {feedback}
        </div>
      ) : null}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h2 className="text-sm font-semibold text-slate-900">Tell the business once you’ve paid</h2>
        <p className="mt-2 text-sm text-slate-600">
          Tap the button after completing the transfer. The business will double-check and send your receipt once the payment clears.
        </p>
        <button
          type="button"
          onClick={handleConfirmTransfer}
          disabled={isSubmitting || isAwaiting || isPaid || isClosed}
          className="mt-4 w-full rounded-lg bg-brand-primary px-4 py-2 text-sm font-semibold text-white transition hover:bg-brand-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isPaid ? "Already marked as paid" : isAwaiting ? "Waiting for confirmation" : isSubmitting ? "Sending..." : "I’ve sent the transfer"}
        </button>
      </section>

      <footer className="pb-10 text-center text-xs text-slate-500">
        Having trouble? Contact the business directly to confirm your payment.
      </footer>
    </div>
  );
}
