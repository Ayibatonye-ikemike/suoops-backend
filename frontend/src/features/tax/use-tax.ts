"use client";

import { useQuery, UseQueryResult } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

// ---------------- Types (lightweight; mirror backend keys we rely on) ----------------

export interface TaxProfileSummary {
  business_size: string;
  classification: string;
  tax_rates: Record<string, string | number>;
  small_business_benefits?: boolean;
}

export interface SmallBusinessCheck {
  eligible: boolean;
  business_size: string;
  tax_rates: Record<string, string | number>;
}

export interface ComplianceSummary {
  compliance_status: string;
  compliance_score: number;
  requirements: Record<string, boolean>;
  next_actions: string[];
  business_size: string;
  small_business_benefits?: boolean;
  last_check?: string | null;
}

export interface VatMonthSummary {
  tax_period: string; // alias of period
  period?: string; // original key retained
  invoices: number;
  taxable_sales: string | number;
  vat_due: string | number;
}

export interface VatSummary {
  current_month: VatMonthSummary;
  registered: boolean;
  last_filing?: string | null;
}

// ---------------- Fetchers ----------------

async function fetchTaxProfile(): Promise<TaxProfileSummary> {
  const { data } = await apiClient.get<TaxProfileSummary>("/tax/profile");
  return data;
}

async function fetchCompliance(): Promise<ComplianceSummary> {
  const { data } = await apiClient.get<ComplianceSummary>("/tax/compliance");
  return data;
}

async function fetchSmallBusiness(): Promise<SmallBusinessCheck> {
  const { data } = await apiClient.get<SmallBusinessCheck>("/tax/small-business-check");
  return data;
}

async function fetchVatSummary(): Promise<VatSummary> {
  const { data } = await apiClient.get<VatSummary>("/tax/vat/summary");
  return data;
}

// ---------------- Hooks ----------------
// Domain data is fairly stable; use extended staleTime to reduce background refetch noise.
// Use gcTime longer than global defaults to keep cached tax data while user navigates dashboard.
const PROFILE_STALE = 10 * 60_000; // 10 minutes
const PROFILE_GC = 30 * 60_000; // 30 minutes

export function useTaxProfile(): UseQueryResult<TaxProfileSummary> {
  return useQuery({
    queryKey: ["taxProfile"],
    queryFn: fetchTaxProfile,
    staleTime: PROFILE_STALE,
    gcTime: PROFILE_GC,
  });
}

export function useTaxCompliance(): UseQueryResult<ComplianceSummary> {
  return useQuery({
    queryKey: ["taxCompliance"],
    queryFn: fetchCompliance,
    staleTime: PROFILE_STALE,
    gcTime: PROFILE_GC,
  });
}

export function useSmallBusinessEligibility(): UseQueryResult<SmallBusinessCheck> {
  return useQuery({
    queryKey: ["smallBusinessEligibility"],
    queryFn: fetchSmallBusiness,
    staleTime: PROFILE_STALE,
    gcTime: PROFILE_GC,
  });
}

export function useVatSummary(): UseQueryResult<VatSummary> {
  return useQuery({
    queryKey: ["vatSummary"],
    queryFn: fetchVatSummary,
    staleTime: 5 * 60_000, // VAT might change with new invoices; keep moderately fresh
    gcTime: 20 * 60_000,
  });
}

// ---------------- Invalidation helpers (optional for mutation flows) ----------------
// Example usage after profile update:
//   const qc = useQueryClient(); qc.invalidateQueries({ queryKey: ["taxProfile"] }); qc.invalidateQueries({ queryKey: ["taxCompliance"] });
export const TAX_QUERY_KEYS = {
  profile: ["taxProfile"] as const,
  compliance: ["taxCompliance"] as const,
  smallBusiness: ["smallBusinessEligibility"] as const,
  vat: ["vatSummary"] as const,
};
