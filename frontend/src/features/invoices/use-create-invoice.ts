"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

import { type Invoice } from "./use-invoices";

export type InvoiceLineInput = components["schemas"]["InvoiceLineIn"];
export type InvoiceCreatePayload = components["schemas"]["InvoiceCreate"];

async function createInvoice(payload: InvoiceCreatePayload): Promise<Invoice> {
  const { data } = await apiClient.post<Invoice>("/invoices/", payload);
  return data;
}

export function useCreateInvoice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createInvoice,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}
