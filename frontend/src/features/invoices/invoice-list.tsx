"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { InvoiceDetailPanel } from "./invoice-detail";
import { invoiceStatusHelpText, invoiceStatusLabels } from "./status-map";
import { type Invoice, useInvoices } from "./use-invoices";

export function InvoiceList() {
  const { data, isLoading, error, isFetching, dataUpdatedAt, refetch } = useInvoices();
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const invoices = useMemo(() => data ?? [], [data]);
  
  // Filter invoices by status and search query
  const filteredInvoices = useMemo(() => {
    let filtered = invoices;
    
    // Apply status filter
    if (statusFilter !== "all") {
      filtered = filtered.filter((inv) => inv.status === statusFilter);
    }
    
    // Apply search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      filtered = filtered.filter(
        (inv) =>
          inv.invoice_id.toLowerCase().includes(query) ||
          inv.amount.toString().includes(query)
      );
    }
    
    return filtered;
  }, [invoices, statusFilter, searchQuery]);
  
  const hasInvoices = invoices.length > 0;
  const hasFilteredInvoices = filteredInvoices.length > 0;
  
  // Status counts for filter badges
  const statusCounts = useMemo(() => {
    return {
      all: invoices.length,
      pending: invoices.filter((inv) => inv.status === "pending").length,
      awaiting_confirmation: invoices.filter((inv) => inv.status === "awaiting_confirmation").length,
      paid: invoices.filter((inv) => inv.status === "paid").length,
    };
  }, [invoices]);

  useEffect(() => {
    if (!hasInvoices) {
      setSelectedInvoiceId(null);
      return;
    }
    if (selectedInvoiceId && filteredInvoices.some((invoice) => invoice.invoice_id === selectedInvoiceId)) {
      return;
    }
    if (filteredInvoices.length > 0) {
      setSelectedInvoiceId(filteredInvoices[0].invoice_id);
    } else {
      setSelectedInvoiceId(null);
    }
  }, [hasInvoices, filteredInvoices, selectedInvoiceId]);

  const lastUpdated = useMemo(() => {
    if (!dataUpdatedAt) {
      return null;
    }
    return new Date(dataUpdatedAt).toLocaleTimeString();
  }, [dataUpdatedAt]);

  if (isLoading) {
    return <p>Loading invoices...</p>;
  }

  if (error) {
    return <p>Failed to load invoices. Please refresh.</p>;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3 text-sm text-slate-500">
          <span>Keep invoice statuses in sync after you confirm customer payments.</span>
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-2 rounded-lg border border-brand-primary bg-brand-primary px-3 py-1.5 font-semibold text-white transition hover:bg-brand-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isFetching ? "Refreshing…" : "Refresh"}
          </button>
          {lastUpdated ? <span className="ml-auto italic">Updated {lastUpdated}</span> : null}
        </div>

        {/* Search Bar */}
        <input
          type="text"
          placeholder="Search by invoice ID or amount..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-900 outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
        />

        {/* Status Filter Buttons */}
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => setStatusFilter("all")}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              statusFilter === "all"
                ? "bg-brand-primary text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            All ({statusCounts.all})
          </button>
          <button
            onClick={() => setStatusFilter("pending")}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              statusFilter === "pending"
                ? "bg-amber-500 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Pending ({statusCounts.pending})
          </button>
          <button
            onClick={() => setStatusFilter("awaiting_confirmation")}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              statusFilter === "awaiting_confirmation"
                ? "bg-blue-500 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Awaiting ({statusCounts.awaiting_confirmation})
          </button>
          <button
            onClick={() => setStatusFilter("paid")}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              statusFilter === "paid"
                ? "bg-emerald-500 text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            Paid ({statusCounts.paid})
          </button>
        </div>

        {hasFilteredInvoices ? (
          <ul className="grid gap-3">
            {filteredInvoices.map((invoice: Invoice) => {
              const status = invoiceStatusLabels[invoice.status] ?? {
                label: invoice.status,
                tone: "neutral" as const,
              };
              const helpText = invoiceStatusHelpText[invoice.status];
              const isSelected = selectedInvoiceId === invoice.invoice_id;
              const borderClass =
                status.tone === "success"
                  ? "border-emerald-200"
                  : status.tone === "warning"
                    ? "border-amber-200"
                    : status.tone === "danger"
                      ? "border-rose-200"
                      : "border-slate-200";

              const selectInvoice = () => setSelectedInvoiceId(invoice.invoice_id);

              return (
                <li key={invoice.invoice_id}>
                  <div
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    onClick={selectInvoice}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        selectInvoice();
                      }
                    }}
                    className={`rounded-2xl border bg-white p-5 text-left shadow-sm transition ${borderClass} ${
                      isSelected ? "ring-2 ring-brand-primary" : "hover:shadow-md"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3 text-sm">
                      <strong className="font-semibold text-slate-900">{invoice.invoice_id}</strong>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
                        {status.label}
                      </span>
                    </div>
                    <p className="text-2xl font-bold text-slate-900">₦ {invoice.amount}</p>
                    {helpText ? <p className="text-sm text-slate-500">{helpText}</p> : null}
                    <div className="mt-3 flex flex-wrap items-center gap-3">
                      {invoice.pdf_url ? (
                        <Link
                          href={`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000"}/invoices/${invoice.invoice_id}/pdf`}
                          target="_blank"
                          className="inline-flex items-center gap-2 text-sm font-semibold text-brand-primary hover:underline"
                          onClick={(event) => event.stopPropagation()}
                        >
                          📄 View PDF
                        </Link>
                      ) : null}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : hasInvoices ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-500">
            No invoices match your filters.
            <button
              onClick={() => {
                setStatusFilter("all");
                setSearchQuery("");
              }}
              className="mt-2 block w-full rounded-lg bg-brand-primary px-4 py-2 text-white hover:bg-brand-primary/90"
            >
              Clear Filters
            </button>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-sm text-slate-500">
            No invoices yet. Create one from WhatsApp or the API to see it here.
          </div>
        )}
      </div>

      <InvoiceDetailPanel invoiceId={hasFilteredInvoices ? selectedInvoiceId : null} />
    </div>
  );
}
