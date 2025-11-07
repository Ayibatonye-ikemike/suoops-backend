"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { TAX_QUERY_KEYS } from "./use-tax";

export interface TaxProfileUpdateRequest {
  annual_turnover?: number;
  fixed_assets?: number;
  tin?: string;
  vat_registration_number?: string;
  vat_registered?: boolean;
}

export interface TaxProfileUpdateResponse {
  message: string;
  summary: unknown; // Rely on downstream typing from useTaxProfile consumer
}

async function updateTaxProfile(data: TaxProfileUpdateRequest): Promise<TaxProfileUpdateResponse> {
  const { data: resp } = await apiClient.post<TaxProfileUpdateResponse>("/tax/profile", data);
  return resp;
}

export function useUpdateTaxProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: updateTaxProfile,
    onSuccess: () => {
      // Invalidate related cached tax data for fresh re-fetch
      qc.invalidateQueries({ queryKey: TAX_QUERY_KEYS.profile });
      qc.invalidateQueries({ queryKey: TAX_QUERY_KEYS.compliance });
      qc.invalidateQueries({ queryKey: TAX_QUERY_KEYS.smallBusiness });
      qc.invalidateQueries({ queryKey: TAX_QUERY_KEYS.vat });
    },
  });
}
