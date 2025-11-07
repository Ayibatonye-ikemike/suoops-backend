"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

export type InvoiceDetail = components["schemas"]["InvoiceOutDetailed"];

async function fetchInvoiceDetail(invoiceId: string): Promise<InvoiceDetail> {
  const { data } = await apiClient.get<InvoiceDetail>(`/invoices/${invoiceId}`);
  return data;
}

export function useInvoiceDetail(invoiceId: string | null) {
  return useQuery({
    queryKey: ["invoice", invoiceId],
    queryFn: () => fetchInvoiceDetail(invoiceId as string),
    enabled: Boolean(invoiceId),
  });
}
