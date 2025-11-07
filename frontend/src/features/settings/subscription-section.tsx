"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";
import { PlanSelectionModal } from "./plan-selection-modal";

type SubscriptionPlan = "FREE" | "STARTER" | "PRO" | "BUSINESS" | "ENTERPRISE";

interface PlanDetails {
  name: string;
  price: string;
  limit: string;
  features: string[];
}

const PLAN_DETAILS: Record<SubscriptionPlan, PlanDetails> = {
  FREE: {
    name: "Free",
    price: "₦0/month",
    limit: "5 invoices/month",
    features: ["Basic invoice generation", "PDF exports", "WhatsApp integration"],
  },
  STARTER: {
    name: "Starter",
    price: "₦2,500/month",
    limit: "100 invoices/month",
    features: ["WhatsApp invoicing", "PDF generation", "Email delivery", "Payment tracking"],
  },
  PRO: {
    name: "Pro",
    price: "₦7,500/month",
    limit: "1,000 invoices/month",
    features: ["Everything in Starter", "Logo branding", "Phone verification", "Voice notes"],
  },
  BUSINESS: {
    name: "Business",
    price: "₦15,000/month",
    limit: "3,000 invoices/month",
    features: ["Everything in Pro", "Priority processing", "Email support", "Lower rates"],
  },
  ENTERPRISE: {
    name: "Enterprise",
    price: "₦50,000/month",
    limit: "Unlimited invoices",
    features: ["Everything in Business", "Custom features", "Direct support", "Volume discount"],
  },
};

export function SubscriptionSection() {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const { data: user, isLoading, error } = useQuery({
    queryKey: ["currentUser"],
    queryFn: async () => {
      const response = await apiClient.get("/users/me");
      return response.data;
    },
    retry: false,
    staleTime: 60000, // 1 minute
  });

  if (isLoading) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-1/3 rounded bg-slate-200" />
          <div className="h-20 w-full rounded bg-slate-200" />
        </div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <p className="text-sm text-slate-500">Unable to load subscription details.</p>
      </div>
    );
  }

  const currentPlan = (user?.plan || "FREE") as SubscriptionPlan;
  const planDetails = PLAN_DETAILS[currentPlan] || PLAN_DETAILS.FREE;
  const invoicesUsed = user?.invoices_this_month || 0;
  const invoiceLimit = currentPlan === "ENTERPRISE" ? "∞" : (planDetails.limit?.split(" ")[0] || "5");

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-6 py-4">
        <h2 className="text-lg font-semibold text-slate-900">Subscription Plan</h2>
        <p className="mt-1 text-sm text-slate-500">
          Manage your subscription and view usage
        </p>
      </div>
      <div className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-blue-100">
                <span className="text-2xl">
                  {currentPlan === "FREE" && "🆓"}
                  {currentPlan === "STARTER" && "🚀"}
                  {currentPlan === "PRO" && "⭐"}
                  {currentPlan === "BUSINESS" && "💼"}
                  {currentPlan === "ENTERPRISE" && "👑"}
                </span>
              </div>
              <div>
                <h3 className="text-xl font-semibold text-slate-900">
                  {planDetails.name} Plan
                </h3>
                <p className="text-sm text-slate-500">{planDetails.price}</p>
              </div>
            </div>

            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-600">Invoice usage this month</span>
                <span className="font-semibold text-slate-900">
                  {invoicesUsed} of {invoiceLimit}
                </span>
              </div>
              {currentPlan !== "ENTERPRISE" && (
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all"
                    style={{
                      width: `${Math.min((invoicesUsed / parseInt(invoiceLimit)) * 100, 100)}%`,
                    }}
                  />
                </div>
              )}
            </div>

            <div className="mt-4">
              <p className="text-sm font-medium text-slate-700">Plan features:</p>
              <ul className="mt-2 space-y-1">
                {planDetails.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-slate-600">
                    <span className="text-green-500">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>

        {currentPlan !== "ENTERPRISE" && (
          <div className="mt-6 rounded-lg bg-blue-50 p-4">
            <p className="text-sm text-blue-900">
              💡 <strong>Want more invoices?</strong> Upgrade your plan to increase your monthly
              limit and unlock advanced features.
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Upgrade Plan
            </button>
          </div>
        )}

        {/* Plan Selection Modal */}
        <PlanSelectionModal
          isOpen={isModalOpen}
          onClose={() => setIsModalOpen(false)}
          currentPlan={currentPlan}
        />
      </div>
    </div>
  );
}
