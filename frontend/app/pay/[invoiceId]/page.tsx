import { notFound } from "next/navigation";

import { getConfig } from "@/lib/config";
import { InvoiceClient } from "./invoice-client";
import type { components } from "@/api/types";

type InvoicePublic = components["schemas"]["InvoicePublicOut"];
type RouteParams = { invoiceId: string };
type RouteProps = { params: Promise<RouteParams> };

export const dynamic = "force-dynamic";

async function fetchInvoice(invoiceId: string, apiBaseUrl: string): Promise<InvoicePublic | null> {
  const response = await fetch(`${apiBaseUrl}/public/invoices/${invoiceId}`, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error("Unable to load invoice. Please try again later.");
  }

  return (await response.json()) as InvoicePublic;
}

export default async function PayInvoicePage({ params }: RouteProps) {
  const { invoiceId } = await params;
  const { apiBaseUrl } = getConfig();
  const invoice = await fetchInvoice(invoiceId, apiBaseUrl);

  if (!invoice) {
    notFound();
  }

  return <InvoiceClient initialInvoice={invoice} invoiceId={invoiceId} apiBaseUrl={apiBaseUrl} />;
}
