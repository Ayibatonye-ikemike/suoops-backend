"use client";

import { useState } from "react";

interface RegulatoryNoticeProps {
  variant?: "tax" | "vat" | "general";
  className?: string;
}

/**
 * RegulatoryNotice
 * Unified lightweight disclaimer & context block for fiscalization and tax features.
 * Provides SuoOps platform summary and clarifies provisional nature of integrations.
 */
export function RegulatoryNotice({ variant = "general", className = "" }: RegulatoryNoticeProps) {
  const [expanded, setExpanded] = useState(false);

  const headingMap: Record<string, string> = {
    tax: "Tax & Fiscalization (Preview)",
    vat: "VAT & Filing Guidance (Preview)",
    general: "Regulatory Context (Preview)"
  };

  return (
    <div className={`rounded-lg border border-blue-200 bg-blue-50 p-4 ${className}`}> 
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-blue-900">{headingMap[variant]}</h3>
        <button
          type="button"
          onClick={() => setExpanded(e => !e)}
          className="text-xs px-2 py-1 rounded border border-blue-300 bg-white text-blue-700 hover:bg-blue-100"
          aria-expanded={expanded}
        >
          {expanded ? "Hide" : "Details"}
        </button>
      </div>
      {!expanded && (
        <p className="text-xs text-blue-700">
          SuoOps simplifies invoicing & compliance via WhatsApp. Fiscalization gateway integration is pending regulator API credentials.
        </p>
      )}
      {expanded && (
        <div className="space-y-2 text-xs text-blue-800 leading-relaxed">
          <p>
            <strong>SuoOps</strong> is a WhatsApp-first automation platform for micro and informal businesses in Nigeria. Users create and send invoices using simple voice notes or text messages—no app installs or training required.
          </p>
          <p>
            We leverage AI/NLP to formalise transactions, accelerate payments, and reduce friction. The newly added tax & compliance features are <strong>provisional</strong>: final integration with the fiscalization authority (FIRS / prospective NBR gateway) awaits issuance of production credentials.
          </p>
          <p>
            Displayed tax rates, exemptions and small business thresholds are illustrative; confirm with current Federal Inland Revenue Service guidance. This interface does not constitute legal or financial advice.
          </p>
          <p className="text-[10px] opacity-70">© {new Date().getFullYear()} SuoOps. Informational preview only. Subject to regulatory updates.</p>
        </div>
      )}
    </div>
  );
}

export default RegulatoryNotice;
