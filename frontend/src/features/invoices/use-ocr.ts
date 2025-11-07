/**
 * OCR API Hooks - React Query hooks for photo-to-invoice OCR
 */

import { useMutation } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// OCR parse response type
export interface OCRItem {
  description: string;
  quantity: number;
  unit_price: string;
}

export interface OCRParseResult {
  success: boolean;
  customer_name: string;
  business_name: string | null;
  amount: string;
  currency: string;
  items: OCRItem[];
  date: string | null;
  confidence: "high" | "medium" | "low";
  raw_text: string;
  error?: string;
}

/**
 * Parse receipt image to extract invoice data
 */
export function useParseReceipt() {
  return useMutation<OCRParseResult, Error, { file: File; context?: string }>({
    mutationFn: async ({ file, context }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (context) {
        formData.append("context", context);
      }

      const response = await apiClient.post("/ocr/parse", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      return response.data;
    },
  });
}

/**
 * Parse image and create invoice in one step
 */
export interface CreateInvoiceResponse {
  invoice_id: string;
  customer_name: string;
  amount: number;
  currency: string;
  created_at: string;
}

export function useCreateInvoiceFromPhoto() {
  return useMutation<
    CreateInvoiceResponse,
    Error,
    { file: File; customerPhone?: string; context?: string }
  >({
    mutationFn: async ({ file, customerPhone, context }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (customerPhone) {
        formData.append("customer_phone", customerPhone);
      }
      if (context) {
        formData.append("context", context);
      }

      const response = await apiClient.post<CreateInvoiceResponse>("/ocr/create-invoice", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      return response.data;
    },
  });
}
