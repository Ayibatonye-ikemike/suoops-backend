"use client";

import { useState } from "react";
import { isAxiosError } from "axios";

import { useCreateInvoice, type InvoiceLineInput } from "./use-create-invoice";
import { PlanSelectionModal } from "../settings/plan-selection-modal";

type LineDraft = InvoiceLineInput & { id: string };

const makeId = () => {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return Math.random().toString(36).slice(2, 9);
};

const emptyLine = (): LineDraft => ({ id: makeId(), description: "", quantity: 1, unit_price: 0 });

export function InvoiceCreateForm() {
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [amount, setAmount] = useState("");
  const [lines, setLines] = useState<LineDraft[]>([emptyLine()]);
  const [lastPdfUrl, setLastPdfUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [quotaError, setQuotaError] = useState<string | null>(null);
  const [currentPlan, setCurrentPlan] = useState<string>("FREE");

  const mutation = useCreateInvoice();

  function updateLine(id: string, patch: Partial<LineDraft>) {
    setLines((current) => current.map((line) => (line.id === id ? { ...line, ...patch } : line)));
  }

  function removeLine(id: string) {
    setLines((current) => (current.length === 1 ? current : current.filter((line) => line.id !== id)));
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setLastPdfUrl(null);
    const parsedAmount = Number(amount);
    if (!customerName || Number.isNaN(parsedAmount) || parsedAmount <= 0) {
      setError("Customer name and a positive amount are required.");
      return;
    }
    const preparedLines = lines
      .filter((line) => line.description.trim())
      .map<InvoiceLineInput>((line) => ({
        description: line.description.trim(),
        quantity: Number(line.quantity) || 1,
        unit_price: Number(line.unit_price) || 0,
      }));

    try {
      const invoice = await mutation.mutateAsync({
        customer_name: customerName,
        customer_phone: customerPhone || undefined,
        customer_email: customerEmail || undefined,
        amount: parsedAmount,
        lines: preparedLines.length > 0 ? preparedLines : [{ description: "Item", quantity: 1, unit_price: parsedAmount }],
      });
      setLastPdfUrl(invoice.pdf_url ?? null);
      setCustomerName("");
      setCustomerPhone("");
      setCustomerEmail("");
      setAmount("");
      setLines([emptyLine()]);
    } catch (submitError) {
      console.error(submitError);
      
      // Check if it's a quota limit error
      if (isAxiosError(submitError) && submitError.response?.status === 400) {
        const errorMessage = submitError.response?.data?.detail || "";
        if (errorMessage.includes("Invoice limit reached") || errorMessage.includes("Upgrade")) {
          setQuotaError(errorMessage);
          setShowUpgradeModal(true);
          
          // Extract current plan from error message or default to FREE
          if (errorMessage.includes("Starter")) setCurrentPlan("FREE");
          else if (errorMessage.includes("Pro")) setCurrentPlan("STARTER");
          else if (errorMessage.includes("Business")) setCurrentPlan("PRO");
          else setCurrentPlan("FREE");
          
          return;
        }
      }
      
      setError("Failed to create invoice. Check inputs and try again.");
    }
  }

  return (
    <form className="flex flex-col gap-6" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <h2 className="text-xl font-semibold text-slate-900">Create Invoice</h2>
        <p className="text-sm text-slate-500">Set customer details and line items to generate a payment-ready invoice.</p>
      </div>
      
      {/* OCR Photo Upload Option */}
      <div className="rounded-lg border-2 border-dashed border-blue-300 bg-blue-50 p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className="text-2xl">📸</span>
              <h3 className="font-semibold text-blue-900">Create from Photo</h3>
            </div>
            <p className="mt-1 text-sm text-blue-700">
              Take a photo of a receipt and AI will extract the details automatically
            </p>
          </div>
          <a
            href="/dashboard/invoices/create-from-photo"
            className="whitespace-nowrap rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
          >
            Upload Photo
          </a>
        </div>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="flex flex-col gap-2 text-sm font-semibold text-slate-700">
          Customer name
          <input
            value={customerName}
            onChange={(event) => setCustomerName(event.target.value)}
            required
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </label>
        <label className="flex flex-col gap-2 text-sm font-semibold text-slate-700">
          Customer phone
          <input
            value={customerPhone}
            onChange={(event) => setCustomerPhone(event.target.value)}
            placeholder="Optional (e.g., +2348012345678)"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </label>
        <label className="flex flex-col gap-2 text-sm font-semibold text-slate-700">
          Customer email
          <input
            type="email"
            value={customerEmail}
            onChange={(event) => setCustomerEmail(event.target.value)}
            placeholder="Optional (e.g., customer@example.com)"
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </label>
        <label className="flex flex-col gap-2 text-sm font-semibold text-slate-700">
          Total amount
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            type="number"
            min="0"
            step="0.01"
            required
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-base font-normal text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
        </label>
      </div>
      <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <header className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-semibold text-slate-800">Line items</h3>
          <button
            type="button"
            onClick={() => setLines((current) => [...current, emptyLine()])}
            className="inline-flex items-center gap-2 rounded-lg border border-brand-primary bg-brand-primary px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-brand-primary/90"
          >
            Add line
          </button>
        </header>
        <div className="space-y-3">
          {lines.map((line) => (
            <div key={line.id} className="grid gap-3 md:grid-cols-[2fr_repeat(2,_minmax(120px,_1fr))_auto]">
              <input
                value={line.description}
                onChange={(event) => updateLine(line.id, { description: event.target.value })}
                placeholder="Description"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              <input
                type="number"
                min="1"
                value={line.quantity}
                onChange={(event) => updateLine(line.id, { quantity: Number(event.target.value) })}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              <input
                type="number"
                min="0"
                step="0.01"
                value={line.unit_price}
                onChange={(event) => updateLine(line.id, { unit_price: Number(event.target.value) })}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              <button
                type="button"
                onClick={() => removeLine(line.id)}
                disabled={lines.length === 1}
                className="justify-self-start text-sm font-semibold text-rose-600 transition hover:text-rose-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </section>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="w-fit rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {mutation.isPending ? "Creating…" : "Create invoice"}
      </button>
      {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600">{error}</p> : null}
      {quotaError ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-900">⚠️ Invoice Limit Reached</p>
          <p className="mt-1 text-sm text-amber-800">{quotaError}</p>
          <button
            type="button"
            onClick={() => setShowUpgradeModal(true)}
            className="mt-3 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700"
          >
            View Upgrade Options
          </button>
        </div>
      ) : null}
      {lastPdfUrl ? (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
          Invoice ready. {""}
          <a href={lastPdfUrl} target="_blank" rel="noreferrer" className="underline">
            View PDF
          </a>
        </p>
      ) : null}
      
      {/* Upgrade Modal */}
      <PlanSelectionModal
        isOpen={showUpgradeModal}
        onClose={() => setShowUpgradeModal(false)}
        currentPlan={currentPlan}
      />
    </form>
  );
}