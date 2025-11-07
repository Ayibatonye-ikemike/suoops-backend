"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
// Lightweight className merge without external dependency
function cx(...classes: Array<string | undefined | false | null>): string {
  return classes.filter(Boolean).join(" ");
}

interface FiscalizationStatus {
  accredited: boolean;
  generated_count: number;
  pending_external_count: number;
  timestamp: string;
}

interface AccreditationStatusBadgeProps {
  className?: string;
}

export function AccreditationStatusBadge({ className }: AccreditationStatusBadgeProps) {
  const { data, isLoading, isError } = useQuery<FiscalizationStatus>({
    queryKey: ["fiscalization-status"],
    queryFn: async () => {
      const res = await apiClient.get("/tax/fiscalization/status");
      return res.data;
    },
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <span
        className={cx(
          "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium bg-slate-50 border-slate-200 text-slate-500",
          className
        )}
      >
        Checking status…
      </span>
    );
  }

  if (isError || !data) {
    return (
      <span
        className={cx(
          "inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium bg-red-50 border-red-200 text-red-600",
          className
        )}
      >
        Status unavailable
      </span>
    );
  }

  const { accredited, generated_count, pending_external_count } = data;
  const colorClasses = accredited
    ? "bg-emerald-50 border-emerald-200 text-emerald-700"
    : "bg-amber-50 border-amber-200 text-amber-700";

  return (
    <span
      title={
        accredited
          ? `Accredited. ${generated_count} fiscal codes generated.`
          : `Provisional mode. ${generated_count} prepared / ${pending_external_count} pending external.`
      }
      className={cx(
        "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold",
        colorClasses,
        className
      )}
    >
      {accredited ? "Accredited" : "Pre-Accreditation"}
      <span className="font-mono text-[10px] opacity-70">
        {generated_count}/{pending_external_count}
      </span>
    </span>
  );
}
