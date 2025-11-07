"use client";

import { useState } from "react";
import RegulatoryNotice from "@/components/regulatory-notice";
import { AccreditationStatusBadge } from "@/components/accreditation-status-badge";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "@/api/client";

interface TaxProfile {
  business_size: string;
  is_small_business: boolean;
  annual_turnover: number;
  fixed_assets: number;
  tax_rates: {
    CIT: number;
    CGT: number;
    DEV_LEVY: number;
    VAT: number;
  };
  vat_registered: boolean;
  vat_number: string | null;
  tin: string | null;
  firs_registered: boolean;
}

interface ComplianceSummary {
  compliance_status: string;
  compliance_score: number;
  requirements: {
    tin_registered: boolean;
    vat_registered: boolean;
  firs_registered: boolean;
  };
  next_actions: string[];
  business_size: string;
  small_business_benefits: boolean;
}

interface TaxRates {
  CIT: number;
  CGT: number;
  DEV_LEVY: number;
  VAT: number;
}

interface SmallBusinessEligibility {
  eligible: boolean;
  business_size: string;
  current_turnover: number;
  turnover_limit: number;
  turnover_remaining: number;
  current_assets: number;
  assets_limit: number;
  tax_rates: TaxRates;
  benefits: string[];
  approaching_limit: boolean;
}

export default function TaxCompliancePage() {
  const queryClient = useQueryClient();
  const [editMode, setEditMode] = useState(false);
  const [showBenefits, setShowBenefits] = useState(true);
  const [formData, setFormData] = useState({
    annual_turnover: "",
    fixed_assets: "",
    tin: "",
    vat_registration_number: "",
  });

  // Fetch tax profile
  const { data: profile, isLoading: profileLoading } = useQuery<TaxProfile>({
    queryKey: ["taxProfile"],
    queryFn: async () => {
      const response = await apiClient.get("/tax/profile");
      return response.data;
    },
  });

  // Fetch compliance summary
  const { data: compliance } = useQuery<ComplianceSummary>({
    queryKey: ["taxCompliance"],
    queryFn: async () => {
      const response = await apiClient.get("/tax/compliance");
      return response.data;
    },
  });

  // Fetch small business eligibility
  const { data: eligibility } = useQuery<SmallBusinessEligibility>({
    queryKey: ["smallBusinessEligibility"],
    queryFn: async () => {
      const response = await apiClient.get("/tax/small-business-check");
      return response.data;
    },
  });

  // Update tax profile mutation
  type UpdatePayload = Partial<
    Pick<TaxProfile, "annual_turnover" | "fixed_assets" | "tin" | "vat_number"> & { vat_registered?: boolean; vat_registration_number?: string }
  >;

  const updateProfile = useMutation({
    mutationFn: async (data: UpdatePayload) => {
      const response = await apiClient.post("/tax/profile", data);
      return response.data as TaxProfile;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["taxProfile"] });
      queryClient.invalidateQueries({ queryKey: ["taxCompliance"] });
      queryClient.invalidateQueries({ queryKey: ["smallBusinessEligibility"] });
      setEditMode(false);
    },
  });

  const handleSave = () => {
    const data: UpdatePayload = {};
    
    if (formData.annual_turnover) {
      data.annual_turnover = parseFloat(formData.annual_turnover);
    }
    if (formData.fixed_assets) {
      data.fixed_assets = parseFloat(formData.fixed_assets);
    }
    if (formData.tin) {
      data.tin = formData.tin;
    }
    if (formData.vat_registration_number) {
      (data as UpdatePayload).vat_registration_number = formData.vat_registration_number;
      (data as UpdatePayload).vat_registered = true;
    }

    updateProfile.mutate(data);
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat("en-NG", {
      style: "currency",
      currency: "NGN",
      minimumFractionDigits: 0,
    }).format(amount);
  };

  const getComplianceColor = (score: number) => {
    if (score === 100) return "text-green-600 bg-green-50";
    if (score >= 66) return "text-blue-600 bg-blue-50";
    if (score >= 33) return "text-yellow-600 bg-yellow-50";
    return "text-red-600 bg-red-50";
  };

  const formatScore = (score: number) => {
    if (!Number.isFinite(score)) return score;
    // Round to whole number for display; raw value preserved in title tooltip
    return Math.round(score);
  };

  if (profileLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">
          Tax Compliance Dashboard <AccreditationStatusBadge className="align-middle ml-2" />
        </h1>
        <p className="mt-2 text-gray-600">
          Manage your business tax profile and prepare for e-invoicing / fiscalization requirements ("FIRS 2026" indicative)
        </p>
      </div>

  <RegulatoryNotice variant="tax" className="mb-6" />
  {/* Compliance Score */}
      {compliance && (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">
              Compliance Status
            </h2>
            <span
              className={`px-4 py-2 rounded-full font-medium ${getComplianceColor(
                compliance.compliance_score
              )}`}
            >
              <span title={`Exact score: ${compliance.compliance_score}`}>{formatScore(compliance.compliance_score)}% Compliant</span>
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="flex items-center">
              <div
                className={`w-3 h-3 rounded-full mr-2 ${
                  compliance.requirements.tin_registered
                    ? "bg-green-500"
                    : "bg-gray-300"
                }`}
              ></div>
              <span className="text-sm text-gray-700">TIN Registered</span>
            </div>
            <div className="flex items-center">
              <div
                className={`w-3 h-3 rounded-full mr-2 ${
                  compliance.requirements.vat_registered
                    ? "bg-green-500"
                    : "bg-gray-300"
                }`}
              ></div>
              <span className="text-sm text-gray-700">VAT Registered</span>
            </div>
            <div className="flex items-center">
              <div
                className={`w-3 h-3 rounded-full mr-2 ${
                  compliance.requirements.firs_registered
                    ? "bg-green-500"
                    : "bg-gray-300"
                }`}
              ></div>
              <span className="text-sm text-gray-700">FIRS Fiscalization Ready</span>
            </div>
          </div>

          {compliance.next_actions.length > 0 && (
            <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <h3 className="text-sm font-medium text-yellow-800 mb-2">
                Next Actions Required:
              </h3>
              <ul className="list-disc list-inside space-y-1">
                {compliance.next_actions.map((action, idx) => (
                  <li key={idx} className="text-sm text-yellow-700">
                    {action}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Small Business Status */}
      {eligibility && (
        <div
          className={`rounded-lg shadow-sm border p-6 mb-6 ${
            eligibility.eligible
              ? "bg-green-50 border-green-200"
              : "bg-gray-50 border-gray-200"
          }`}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-gray-900">
              {eligibility.eligible
                ? "🎉 Small Business Status"
                : "Business Classification"}
            </h2>
            <span
              className={`px-4 py-2 rounded-full text-sm font-medium ${
                eligibility.eligible
                  ? "bg-green-600 text-white"
                  : "bg-gray-600 text-white"
              }`}
            >
              {eligibility.business_size.toUpperCase()}
            </span>
          </div>

          {eligibility.eligible && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
                <div>
                  <p className="text-sm text-gray-600 mb-1">Annual Turnover</p>
                  <p className="text-lg font-semibold text-gray-900">
                    {formatCurrency(eligibility.current_turnover)}
                  </p>
                  <p className="text-xs text-gray-500">
                    Limit: {formatCurrency(eligibility.turnover_limit)} (
                    {formatCurrency(eligibility.turnover_remaining)} remaining)
                  </p>
                </div>
                <div>
                  <p className="text-sm text-gray-600 mb-1">Fixed Assets</p>
                  <p className="text-lg font-semibold text-gray-900">
                    {formatCurrency(eligibility.current_assets)}
                  </p>
                  <p className="text-xs text-gray-500">
                    Limit: {formatCurrency(eligibility.assets_limit)}
                  </p>
                </div>
              </div>

              <div className="bg-white rounded-lg p-4 mb-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="text-sm font-medium text-gray-900">
                    Your Tax Benefits (FIRS 2026 - illustrative)
                  </h3>
                  <button
                    type="button"
                    onClick={() => setShowBenefits((s) => !s)}
                    className="text-xs px-2 py-1 rounded border border-gray-300 bg-white hover:bg-gray-100"
                  >
                    {showBenefits ? "Hide" : "Show"}
                  </button>
                </div>
                {showBenefits && (
                  <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-3">
                      <div className="text-center">
                        <p className="text-2xl font-bold text-green-600">0%</p>
                        <p className="text-xs text-gray-600">CIT*</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-green-600">0%</p>
                        <p className="text-xs text-gray-600">CGT*</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-green-600">0%</p>
                        <p className="text-xs text-gray-600">Dev Levy*</p>
                      </div>
                      <div className="text-center">
                        <p className="text-2xl font-bold text-blue-600">7.5%</p>
                        <p className="text-xs text-gray-600">VAT</p>
                      </div>
                    </div>
                    <ul className="space-y-1">
                      {eligibility.benefits.map((benefit, idx) => (
                        <li key={idx} className="text-sm text-gray-700 flex items-start">
                          <span className="text-green-500 mr-2">✓</span>
                          {benefit}
                        </li>
                      ))}
                    </ul>
                    <p className="mt-3 text-[10px] text-gray-500">
                      *Illustrative incentives only. Verify current Federal Inland Revenue Service regulations. Not legal advice.
                    </p>
                  </>
                )}
              </div>

              {eligibility.approaching_limit && (
                <div className="bg-yellow-100 border border-yellow-300 rounded-lg p-4">
                  <p className="text-sm font-medium text-yellow-800">
                    ⚠️ Warning: You are approaching the small business threshold!
                  </p>
                  <p className="text-sm text-yellow-700 mt-1">
                    Consider strategies to optimize your business structure and
                    maintain small business benefits.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tax Profile */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-gray-900">Tax Profile</h2>
          {!editMode ? (
            <button
              onClick={() => setEditMode(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Edit Profile
            </button>
          ) : (
            <div className="flex gap-2">
              <button
                onClick={() => setEditMode(false)}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={updateProfile.isPending}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {updateProfile.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Annual Turnover */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Annual Turnover
            </label>
            {editMode ? (
              <input
                type="number"
                value={formData.annual_turnover}
                onChange={(e) =>
                  setFormData({ ...formData, annual_turnover: e.target.value })
                }
                placeholder={profile?.annual_turnover ? profile.annual_turnover.toString() : "0"}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            ) : (
              <p className="text-lg font-semibold text-gray-900">
                {formatCurrency(profile?.annual_turnover || 0)}
              </p>
            )}
          </div>

          {/* Fixed Assets */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Fixed Assets
            </label>
            {editMode ? (
              <input
                type="number"
                value={formData.fixed_assets}
                onChange={(e) =>
                  setFormData({ ...formData, fixed_assets: e.target.value })
                }
                placeholder={profile?.fixed_assets ? profile.fixed_assets.toString() : "0"}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            ) : (
              <p className="text-lg font-semibold text-gray-900">
                {formatCurrency(profile?.fixed_assets || 0)}
              </p>
            )}
          </div>

          {/* TIN */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Tax Identification Number (TIN)
            </label>
            {editMode ? (
              <input
                type="text"
                value={formData.tin}
                onChange={(e) => setFormData({ ...formData, tin: e.target.value })}
                placeholder={profile?.tin || "Enter TIN"}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            ) : (
              <p className="text-lg font-semibold text-gray-900">
                {profile?.tin || "Not registered"}
              </p>
            )}
          </div>

          {/* VAT Number */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              VAT Registration Number
            </label>
            {editMode ? (
              <input
                type="text"
                value={formData.vat_registration_number}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    vat_registration_number: e.target.value,
                  })
                }
                placeholder={profile?.vat_number || "Enter VAT Number"}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            ) : (
              <p className="text-lg font-semibold text-gray-900">
                {profile?.vat_number || "Not registered"}
              </p>
            )}
          </div>
        </div>

        {/* Tax Rates Display */}
        {profile && (
          <div className="mt-6 pt-6 border-t border-gray-200">
            <h3 className="text-sm font-medium text-gray-900 mb-3">
              Applicable Tax Rates
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 mb-1">Company Income Tax</p>
                <p className="text-2xl font-bold text-gray-900">
                  {profile.tax_rates.CIT}%
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 mb-1">Capital Gains Tax</p>
                <p className="text-2xl font-bold text-gray-900">
                  {profile.tax_rates.CGT}%
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 mb-1">Development Levy</p>
                <p className="text-2xl font-bold text-gray-900">
                  {profile.tax_rates.DEV_LEVY}%
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 mb-1">VAT</p>
                <p className="text-2xl font-bold text-gray-900">
                  {profile.tax_rates.VAT}%
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

  {/* Accreditation / Fiscalization Preview Info */}
      <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold text-blue-900 mb-2">
          📋 Federal Inland Revenue Service (FIRS) E-Invoicing (Preview)
        </h3>
        <p className="text-sm text-blue-700 mb-4">
          From 2026, enhanced e-invoicing / fiscalization initiatives are expected. SuoOps will prepare invoices with compliance-ready metadata (QR, unique codes) when required.
        </p>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-blue-900">
              Registration Status:{" "}
              {profile?.firs_registered ? (
                <span className="text-green-600">✓ Registered</span>
              ) : (
                <span className="text-yellow-600">⏳ Pending</span>
              )}
            </p>
            <p className="text-xs text-blue-600 mt-1">
              Invoices will include unique codes & QR verification when fiscalization rules are enforced.
            </p>
          </div>
          {!profile?.firs_registered && (
            <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
              Learn More
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
