"use client";

import { useMutation } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { useState } from "react";

import { initializeSubscription } from "@/api/subscription";

interface PlanModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentPlan: string;
}

interface PlanOption {
  name: string;
  value: string;
  price: string;
  limit: string;
  features: string[];
  icon: string;
  popular?: boolean;
}

const PLANS: PlanOption[] = [
  {
    name: "Starter",
    value: "STARTER",
    price: "₦2,500",
    limit: "100 invoices/month",
    icon: "🚀",
    features: ["WhatsApp invoicing", "PDF generation", "Email delivery", "Payment tracking"],
  },
  {
    name: "Pro",
    value: "PRO",
    price: "₦7,500",
    limit: "1,000 invoices/month",
    icon: "⭐",
    popular: true,
    features: ["Everything in Starter", "Logo branding", "Phone verification", "Voice notes"],
  },
  {
    name: "Business",
    value: "BUSINESS",
    price: "₦15,000",
    limit: "3,000 invoices/month",
    icon: "💼",
    features: ["Everything in Pro", "Priority processing", "Email support", "Lower rates"],
  },
  {
    name: "Enterprise",
    value: "ENTERPRISE",
    price: "₦50,000",
    limit: "Unlimited invoices",
    icon: "👑",
    features: ["Everything in Business", "Custom features", "Direct support", "Volume discount"],
  },
];

export function PlanSelectionModal({ isOpen, onClose, currentPlan }: PlanModalProps) {
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);

  const initializeMutation = useMutation({
    mutationFn: initializeSubscription,
    onSuccess: (data) => {
      // Redirect to Paystack checkout
      window.location.href = data.authorization_url;
    },
    onError: (error: unknown) => {
      const message = isAxiosError(error)
        ? error.response?.data?.detail || error.message
        : error instanceof Error
          ? error.message
          : null;
      alert(message || "Failed to initialize payment. Please try again.");
    },
  });

  if (!isOpen) return null;

  const handleUpgrade = () => {
    if (!selectedPlan) {
      alert("Please select a plan");
      return;
    }
    initializeMutation.mutate(selectedPlan);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="relative max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 text-2xl text-slate-400 hover:text-slate-600"
          disabled={initializeMutation.isPending}
        >
          ×
        </button>

        {/* Header */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-slate-900">Choose Your Plan</h2>
          <p className="mt-2 text-sm text-slate-600">
            Select a plan and pay securely via Paystack. Your plan will be upgraded immediately after
            payment.
          </p>
        </div>

        {/* Plans grid */}
        <div className="grid gap-4 md:grid-cols-2">
          {PLANS.map((plan) => {
            const isCurrent = plan.value === currentPlan;
            const isSelected = plan.value === selectedPlan;

            return (
              <div
                key={plan.value}
                onClick={() => !isCurrent && setSelectedPlan(plan.value)}
                className={`relative cursor-pointer rounded-lg border-2 p-4 transition-all ${
                  isCurrent
                    ? "border-green-300 bg-green-50 opacity-60 cursor-not-allowed"
                    : isSelected
                    ? "border-blue-500 bg-blue-50"
                    : "border-slate-200 hover:border-blue-300"
                } ${plan.popular ? "ring-2 ring-blue-400 ring-offset-2" : ""}`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-blue-600 px-3 py-1 text-xs font-semibold text-white">
                    Most Popular
                  </div>
                )}

                {isCurrent && (
                  <div className="absolute -top-3 right-4 rounded-full bg-green-600 px-3 py-1 text-xs font-semibold text-white">
                    Current Plan
                  </div>
                )}

                <div className="flex items-center gap-3">
                  <div className="text-3xl">{plan.icon}</div>
                  <div>
                    <h3 className="text-lg font-bold text-slate-900">{plan.name}</h3>
                    <p className="text-sm text-slate-600">{plan.limit}</p>
                  </div>
                </div>

                <div className="mt-3">
                  <p className="text-2xl font-bold text-slate-900">
                    {plan.price}
                    <span className="text-sm font-normal text-slate-500">/month</span>
                  </p>
                </div>

                <ul className="mt-4 space-y-2">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2 text-sm text-slate-700">
                      <span className="text-green-500">✓</span>
                      {feature}
                    </li>
                  ))}
                </ul>

                {isSelected && !isCurrent && (
                  <div className="mt-3 rounded-md bg-blue-100 p-2 text-center text-sm font-medium text-blue-800">
                    Selected
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div className="mt-6 flex items-center justify-between border-t border-slate-200 pt-4">
          <p className="text-sm text-slate-600">
            💳 Secure payment powered by <strong>Paystack</strong>
          </p>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              disabled={initializeMutation.isPending}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleUpgrade}
              disabled={!selectedPlan || initializeMutation.isPending}
              className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {initializeMutation.isPending ? "Processing..." : "Proceed to Payment"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
