"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  deleteBankDetails,
  getBankDetails,
  updateBankDetails,
} from "@/api/bank-details";
import {
  DEFAULT_FORM,
  NIGERIAN_BANKS,
} from "./bank-details-form.constants";
import {
  formatAccountNumber,
  getErrorMessage,
  toFormState,
  toPayload,
} from "./bank-details-form.utils";
import type {
  BankDetailsUpdate,
  BankFormState,
} from "./bank-details-form.types";

export function BankDetailsForm() {
  const queryClient = useQueryClient();
  const [formState, setFormState] = useState<BankFormState>(DEFAULT_FORM);
  const [initialValues, setInitialValues] = useState<BankFormState>(DEFAULT_FORM);
  const [successMessage, setSuccessMessage] = useState("");
  const [copiedField, setCopiedField] = useState<keyof BankFormState | null>(null);

  const copiedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: bankDetails, isLoading, isError, error } = useQuery({
    queryKey: ["bankDetails"],
    queryFn: getBankDetails,
  });

  const showSuccess = useCallback((message: string) => {
    setSuccessMessage(message);
    if (successTimeoutRef.current) {
      clearTimeout(successTimeoutRef.current);
    }
    successTimeoutRef.current = setTimeout(() => setSuccessMessage(""), 4000);
  }, []);

  const updateMutation = useMutation({
    mutationFn: (payload: BankDetailsUpdate) => updateBankDetails(payload),
    onSuccess: (updated) => {
      const nextState = toFormState(updated);
      setInitialValues(nextState);
      setFormState(nextState);
      queryClient.setQueryData(["bankDetails"], updated);
      showSuccess("Bank details saved.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteBankDetails,
    onSuccess: () => {
      setInitialValues(DEFAULT_FORM);
      setFormState(DEFAULT_FORM);
      queryClient.invalidateQueries({ queryKey: ["bankDetails"] });
      showSuccess("Bank details cleared.");
    },
  });

  useEffect(() => {
    if (updateMutation.isPending || deleteMutation.isPending) {
      return;
    }
    const nextState = toFormState(bankDetails);
    setInitialValues(nextState);
    setFormState((prev) => ({
      businessName: prev.businessName && bankDetails === undefined ? prev.businessName : nextState.businessName,
      bankName: prev.bankName && bankDetails === undefined ? prev.bankName : nextState.bankName,
      accountNumber: prev.accountNumber && bankDetails === undefined ? prev.accountNumber : nextState.accountNumber,
      accountName: prev.accountName && bankDetails === undefined ? prev.accountName : nextState.accountName,
    }));
  }, [bankDetails, updateMutation.isPending, deleteMutation.isPending]);

  useEffect(() => () => {
    if (copiedTimeoutRef.current) clearTimeout(copiedTimeoutRef.current);
    if (successTimeoutRef.current) clearTimeout(successTimeoutRef.current);
  }, []);

  const handleFieldChange = useCallback(
    (field: keyof BankFormState, value: string) => {
      setFormState((prev) => ({ ...prev, [field]: value }));
      if (updateMutation.isError) updateMutation.reset();
      if (deleteMutation.isError) deleteMutation.reset();
    },
    [deleteMutation, updateMutation],
  );

  const handleAccountNumberChange = useCallback(
    (value: string) => {
      const numeric = value.replace(/\D/g, "").slice(0, 10);
      handleFieldChange("accountNumber", numeric);
    },
    [handleFieldChange],
  );

  const isConfigured = bankDetails?.is_configured ?? false;
  const hasChanges = useMemo(
    () =>
      ["businessName", "bankName", "accountNumber", "accountName"].some(
        (key) => formState[key as keyof BankFormState] !== initialValues[key as keyof BankFormState],
      ),
    [formState, initialValues],
  );

  const canClear = useMemo(
    () => Object.values(initialValues).some((value) => value.length > 0),
    [initialValues],
  );

  const formattedAccountNumber = useMemo(() => (
    formState.accountNumber ? formatAccountNumber(formState.accountNumber) : ""
  ), [formState.accountNumber]);

  const updateError = updateMutation.isError ? getErrorMessage(updateMutation.error) : null;
  const deleteError = deleteMutation.isError ? getErrorMessage(deleteMutation.error) : null;
  const fetchError = isError ? getErrorMessage(error) : null;

  const handleSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (!hasChanges) return;
      updateMutation.mutate(toPayload(formState));
    },
    [formState, hasChanges, updateMutation],
  );

  const handleClear = useCallback(() => {
    if (!canClear || deleteMutation.isPending) {
      return;
    }
    const confirmed =
      typeof window === "undefined" ||
      window.confirm("Remove saved bank details? Invoices will no longer show payment instructions.");
    if (!confirmed) return;
    deleteMutation.mutate();
  }, [canClear, deleteMutation]);

  const handleCopy = useCallback(
    async (field: "accountNumber" | "accountName") => {
      const value = field === "accountNumber" ? formState.accountNumber : formState.accountName;
      if (!value || typeof navigator === "undefined" || !navigator.clipboard) {
        return;
      }
      try {
        await navigator.clipboard.writeText(value);
        setCopiedField(field);
        if (copiedTimeoutRef.current) {
          clearTimeout(copiedTimeoutRef.current);
        }
        copiedTimeoutRef.current = setTimeout(() => setCopiedField(null), 2000);
      } catch (copyError) {
        console.error("Failed to copy bank detail", copyError);
      }
    },
    [formState.accountName, formState.accountNumber],
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-sm text-slate-500">Loading bank details...</div>
      </div>
    );
  }

  if (fetchError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        {fetchError}
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div
        className={`rounded-lg border px-4 py-3 ${
          isConfigured ? "border-green-200 bg-green-50" : "border-amber-200 bg-amber-50"
        }`}
      >
        <div className="flex items-start gap-3">
          <span className="text-xl" aria-hidden>
            {isConfigured ? "✅" : "⚠️"}
          </span>
          <div>
            <p className="text-sm font-medium text-slate-900">
              {isConfigured ? "Bank details configured" : "Bank details incomplete"}
            </p>
            <p className="mt-1 text-xs text-slate-600">
              {isConfigured
                ? "New invoices already include your transfer instructions."
                : "Fill out every field and save to show transfer instructions on invoices."}
            </p>
            {hasChanges && !updateMutation.isPending && !deleteMutation.isPending && (
              <p className="mt-2 text-xs font-medium text-amber-700">You have unsaved changes.</p>
            )}
          </div>
        </div>
      </div>

      {successMessage && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          {successMessage}
        </div>
      )}

      {updateError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {updateError}
        </div>
      )}

      {deleteError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {deleteError}
        </div>
      )}

      <div>
        <label htmlFor="businessName" className="block text-sm font-medium text-slate-700">
          Business Name <span className="text-slate-400">(optional)</span>
        </label>
        <input
          id="businessName"
          type="text"
          value={formState.businessName}
          onChange={(event) => handleFieldChange("businessName", event.target.value)}
          placeholder="Lagos Ventures Ltd"
          autoComplete="organization"
          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20"
        />
        <p className="mt-1 text-xs text-slate-500">
          Appears on invoices and receipts sent to customers.
        </p>
      </div>

      <div>
        <label htmlFor="bankName" className="block text-sm font-medium text-slate-700">
          Bank Name <span className="text-red-500">*</span>
        </label>
        <select
          id="bankName"
          value={formState.bankName}
          onChange={(event) => handleFieldChange("bankName", event.target.value)}
          required
          className="mt-1 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20"
        >
          <option value="">Select your bank</option>
          {NIGERIAN_BANKS.map((bank) => (
            <option key={bank} value={bank}>
              {bank}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-500">Where customers will send their transfers.</p>
      </div>

      <div>
        <label htmlFor="accountNumber" className="block text-sm font-medium text-slate-700">
          Account Number <span className="text-red-500">*</span>
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="accountNumber"
            type="text"
            value={formattedAccountNumber}
            onChange={(event) => handleAccountNumberChange(event.target.value)}
            placeholder="0123 4567 89"
            inputMode="numeric"
            required
            pattern="\d{10}"
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm tracking-[0.2em] focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20"
          />
          <button
            type="button"
            onClick={() => handleCopy("accountNumber")}
            disabled={formState.accountNumber.length !== 10}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
          >
            {copiedField === "accountNumber" ? "Copied!" : "Copy"}
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Nigerian NUBAN numbers are exactly 10 digits. Customers see it with spaces for readability.
        </p>
      </div>

      <div>
        <label htmlFor="accountName" className="block text-sm font-medium text-slate-700">
          Account Name <span className="text-red-500">*</span>
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="accountName"
            type="text"
            value={formState.accountName}
            onChange={(event) => handleFieldChange("accountName", event.target.value)}
            placeholder="Lagos Ventures Ltd"
            autoComplete="name"
            required
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-brand-primary focus:outline-none focus:ring-2 focus:ring-brand-primary/20"
          />
          <button
            type="button"
            onClick={() => handleCopy("accountName")}
            disabled={!formState.accountName}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
          >
            {copiedField === "accountName" ? "Copied!" : "Copy"}
          </button>
        </div>
        <p className="mt-1 text-xs text-slate-500">
          Must match your bank records so customers recognise the beneficiary.
        </p>
      </div>

      <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-4">
        <h3 className="text-sm font-semibold text-slate-900">Invoice Preview</h3>
        <p className="mt-1 text-xs text-slate-500">
          Customers receive these instructions on the PDF and WhatsApp message once you save.
        </p>
        <dl className="mt-4 space-y-2 text-sm text-slate-700">
          <div className="flex items-center justify-between">
            <dt className="font-medium">Bank Name</dt>
            <dd>{formState.bankName || <span className="text-slate-400">Not set</span>}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="font-medium">Account Number</dt>
            <dd>
              {formState.accountNumber ? formatAccountNumber(formState.accountNumber) : (
                <span className="text-slate-400">Not set</span>
              )}
            </dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="font-medium">Account Name</dt>
            <dd>{formState.accountName || <span className="text-slate-400">Not set</span>}</dd>
          </div>
          <div className="flex items-center justify-between">
            <dt className="font-medium">Business Name</dt>
            <dd>{formState.businessName || <span className="text-slate-400">Not set</span>}</dd>
          </div>
        </dl>
      </div>

      <div className="flex flex-col gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xs text-slate-500">
          <span className="text-red-500">*</span> Required fields
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleClear}
            disabled={!canClear || deleteMutation.isPending}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 transition hover:border-slate-400 hover:text-slate-900 disabled:opacity-50"
          >
            {deleteMutation.isPending ? "Clearing..." : "Clear bank details"}
          </button>
          <button
            type="submit"
            disabled={!hasChanges || updateMutation.isPending}
            className="rounded-lg bg-brand-primary px-6 py-2 text-sm font-medium text-white transition hover:bg-brand-primary/90 disabled:opacity-50"
          >
            {updateMutation.isPending ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>
    </form>
  );
}
