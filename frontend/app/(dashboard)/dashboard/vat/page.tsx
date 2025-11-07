"use client";

import { useState } from "react";
import RegulatoryNotice from "@/components/regulatory-notice";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

interface VATCalculation {
  subtotal: number;
  vat_rate: number;
  vat_amount: number;
  total: number;
}

interface VATSummary {
  registered: boolean;
  vat_number: string | null;
  current_month: {
    tax_period: string;
    output_vat: number;
    input_vat: number;
    net_vat: number;
    total_invoices: number;
    fiscalized_invoices: number;
  };
  recent_returns: Array<{
    period: string;
    net_vat: number;
    status: string;
  }>;
  compliance_status: string;
}

export default function VATPage() {
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("standard");
  const [calculation, setCalculation] = useState<VATCalculation | null>(null);

  // Fetch VAT summary
  const { data: summary } = useQuery<VATSummary>({
    queryKey: ["vatSummary"],
    queryFn: async () => {
      const response = await apiClient.get("/tax/vat/summary");
      return response.data;
    },
  });

  const calculateVAT = async () => {
    if (!amount || parseFloat(amount) <= 0) return;

    try {
      const response = await apiClient.get("/tax/vat/calculate", {
        params: { amount: parseFloat(amount), category },
      });
      setCalculation(response.data);
    } catch (error) {
      console.error("VAT calculation failed:", error);
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency: "NGN",
      minimumFractionDigits: 2,
    }).format(value);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "submitted":
        return "bg-green-100 text-green-800";
      case "draft":
        return "bg-yellow-100 text-yellow-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">VAT Management</h1>
        <p className="mt-2 text-gray-600">
          Calculate VAT, track returns, and prepare for evolving fiscalization requirements (illustrative preview)
        </p>
        <RegulatoryNotice variant="vat" className="mt-4" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* VAT Calculator */}
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            VAT Calculator
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Amount (₦)
              </label>
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="Enter amount"
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                VAT Category
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="standard">Standard Rate (7.5%)</option>
                <option value="zero_rated">Zero-Rated (0%)</option>
                <option value="exempt">Exempt</option>
                <option value="export">Export</option>
              </select>
            </div>

            <button
              onClick={calculateVAT}
              disabled={!amount || parseFloat(amount) <= 0}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Calculate VAT
            </button>

            {calculation && (
              <div className="mt-6 bg-gray-50 rounded-lg p-4 space-y-3">
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">Subtotal:</span>
                  <span className="text-lg font-semibold text-gray-900">
                    {formatCurrency(calculation.subtotal)}
                  </span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-sm text-gray-600">
                    VAT ({calculation.vat_rate}%):
                  </span>
                  <span className="text-lg font-semibold text-blue-600">
                    {formatCurrency(calculation.vat_amount)}
                  </span>
                </div>
                <div className="border-t border-gray-200 pt-3 flex justify-between items-center">
                  <span className="text-sm font-medium text-gray-700">Total:</span>
                  <span className="text-2xl font-bold text-gray-900">
                    {formatCurrency(calculation.total)}
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* VAT Category Information */}
          <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-blue-900 mb-2">
              VAT Categories (Illustrative)
            </h3>
            <ul className="space-y-2 text-sm text-blue-700">
              <li>
                <span className="font-medium">Standard (7.5%):</span> Most goods
                and services
              </li>
              <li>
                <span className="font-medium">Zero-Rated (0%):</span> Medical,
                education, basic food, agriculture
              </li>
              <li>
                <span className="font-medium">Exempt:</span> Financial services,
                insurance
              </li>
              <li>
                <span className="font-medium">Export:</span> Goods exported with
                FX repatriation
              </li>
            </ul>
          </div>
        </div>

        {/* VAT Summary */}
        {summary && (
          <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              VAT Overview
            </h2>

            {/* Registration Status */}
            <div className="mb-6 p-4 rounded-lg bg-gray-50">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">
                  VAT Registration:
                </span>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    summary.registered
                      ? "bg-green-100 text-green-800"
                      : "bg-yellow-100 text-yellow-800"
                  }`}
                >
                  {summary.registered ? "Registered" : "Not Registered"}
                </span>
              </div>
              {summary.vat_number && (
                <p className="text-sm text-gray-600">
                  VAT Number: {summary.vat_number}
                </p>
              )}
            </div>

            {/* Current Month */}
            <div className="mb-6">
              <h3 className="text-sm font-medium text-gray-700 mb-3">
                Current Month ({summary.current_month.tax_period})
              </h3>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-green-50 rounded-lg p-3">
                  <p className="text-xs text-gray-600 mb-1">Output VAT</p>
                  <p className="text-lg font-bold text-green-600">
                    {formatCurrency(summary.current_month.output_vat)}
                  </p>
                </div>
                <div className="bg-blue-50 rounded-lg p-3">
                  <p className="text-xs text-gray-600 mb-1">Input VAT</p>
                  <p className="text-lg font-bold text-blue-600">
                    {formatCurrency(summary.current_month.input_vat)}
                  </p>
                </div>
                <div className="bg-purple-50 rounded-lg p-3 col-span-2">
                  <p className="text-xs text-gray-600 mb-1">Net VAT Payable</p>
                  <p className="text-2xl font-bold text-purple-600">
                    {formatCurrency(summary.current_month.net_vat)}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-2 gap-4">
                <div>
                  <p className="text-xs text-gray-600">Total Invoices</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {summary.current_month.total_invoices}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-600">Fiscalized</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {summary.current_month.fiscalized_invoices}
                  </p>
                </div>
              </div>
            </div>

            {/* Recent Returns */}
            {summary.recent_returns && summary.recent_returns.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-3">
                  Recent VAT Returns
                </h3>
                <div className="space-y-2">
                  {summary.recent_returns.map((ret, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {ret.period}
                        </p>
                        <p className="text-xs text-gray-600">
                          {formatCurrency(ret.net_vat)}
                        </p>
                      </div>
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(
                          ret.status
                        )}`}
                      >
                        {ret.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Generate Return Button */}
            <button className="w-full mt-6 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Generate VAT Return
            </button>
          </div>
        )}
      </div>

      {/* Information Panel */}
      <div className="mt-6 bg-yellow-50 border border-yellow-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-yellow-900 mb-2">
          💡 VAT Compliance Tips
        </h3>
        <ul className="space-y-2 text-sm text-yellow-700">
          <li className="flex items-start">
            <span className="mr-2">•</span>
            <span>
              VAT returns must be filed monthly before the 21st of the following
              month
            </span>
          </li>
          <li className="flex items-start">
            <span className="mr-2">•</span>
            <span>
              Keep records of all zero-rated and exempt transactions for input VAT
              recovery
            </span>
          </li>
          <li className="flex items-start">
            <span className="mr-2">•</span>
            <span>
              Ensure all invoices are fiscalized before including in VAT returns
            </span>
          </li>
          <li className="flex items-start">
            <span className="mr-2">•</span>
            <span>
              Medical, educational, and basic food items qualify for zero-rating
            </span>
          </li>
        </ul>
      </div>
    </div>
  );
}
