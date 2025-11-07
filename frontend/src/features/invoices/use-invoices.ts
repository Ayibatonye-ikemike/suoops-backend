"use client";

import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

export type Invoice = components["schemas"]["InvoiceOut"];

async function fetchInvoices(): Promise<Invoice[]> {
  const { data } = await apiClient.get<Invoice[]>("/invoices/");
  return data;
}

export function useInvoices() {
  return useQuery({
    queryKey: ["invoices"],
    queryFn: fetchInvoices,
  });
}
