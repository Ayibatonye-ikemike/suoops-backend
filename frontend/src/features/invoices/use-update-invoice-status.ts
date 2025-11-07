"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

type InvoiceDetail = components["schemas"]["InvoiceOutDetailed"];
type InvoiceStatusUpdate = components["schemas"]["InvoiceStatusUpdate"];

async function updateInvoiceStatus(
  invoiceId: string,
  status: InvoiceStatusUpdate["status"],
): Promise<InvoiceDetail> {
  const { data } = await apiClient.patch<InvoiceDetail>(`/invoices/${invoiceId}`, { status });
  return data;
}

export function useUpdateInvoiceStatus(invoiceId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (status: InvoiceStatusUpdate["status"]) => updateInvoiceStatus(invoiceId as string, status),
    onSuccess: (data) => {
      if (!invoiceId) {
        return;
      }
      queryClient.setQueryData(["invoice", invoiceId], data);
      queryClient.invalidateQueries({ queryKey: ["invoices"] });
    },
  });
}
