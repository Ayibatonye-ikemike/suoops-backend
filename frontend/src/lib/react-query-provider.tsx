"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

/**
 * Global React Query provider with sensible defaults:
 * - staleTime: 60s standard (most data is relatively static, prevents refetch spam)
 * - cacheTime: 5 minutes (reclaim memory reasonably fast in low-memory scenarios)
 * - refetchOnWindowFocus: disabled (avoid surprising UI jumps during invoicing/data entry)
 * - retry: 2 (transient network hiccups) with exponential backoff handled internally
 *
 * Domain-specific hooks (e.g. tax profile/compliance) override with longer staleTime.
 */
export function ReactQueryProvider({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000, // 1 minute generic
            gcTime: 5 * 60_000, // 5 minutes (renamed from cacheTime in TanStack v5)
            refetchOnWindowFocus: false,
            retry: 2,
          },
        },
      })
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
