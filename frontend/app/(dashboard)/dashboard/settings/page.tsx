"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import type { components } from "@/api/types";
import { BankDetailsForm } from "@/features/settings/bank-details-form";
import { SubscriptionSection } from "@/features/settings/subscription-section";
import { LogoUpload } from "@/features/settings/logo-upload";
import { PhoneNumberSection } from "@/features/settings/phone-number-section";

type CurrentUser = components["schemas"]["UserOut"];

export default function SettingsPage() {
  const { data: user, error } = useQuery<CurrentUser>({
    queryKey: ["currentUser"],
    queryFn: async () => {
      const response = await apiClient.get<CurrentUser>("/users/me");
      return response.data;
    },
    retry: false,
    staleTime: 60000,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="mt-1 text-sm text-slate-500">
          Manage your business account and payment settings
        </p>
      </div>

      {/* Subscription Plan */}
      <SubscriptionSection />

      {/* Phone Number Verification */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">WhatsApp Number</h2>
          <p className="mt-1 text-sm text-slate-500">
            Add your WhatsApp number to enable login and receive invoice notifications
          </p>
        </div>
        <div className="p-6">
          <PhoneNumberSection 
            currentPhone={user?.phone_verified && user?.phone ? user.phone : null} 
          />
        </div>
      </div>

      {/* Business Branding */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Business Branding</h2>
          <p className="mt-1 text-sm text-slate-500">
            Upload your business logo to appear on invoices and receipts
          </p>
        </div>
        <div className="p-6">
          <LogoUpload />
        </div>
      </div>

      {/* Bank Account Details */}
      <div className="rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">Bank Account Details</h2>
          <p className="mt-1 text-sm text-slate-500">
            Configure your bank account to receive customer payments via bank transfer
          </p>
        </div>
        <div className="p-6">
          <BankDetailsForm />
        </div>
      </div>
    </div>
  );
}
