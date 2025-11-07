/**
 * OCR Review Modal Component
 * Displays extracted OCR data and allows user to review/edit before creating invoice
 */

"use client";

import { useState } from "react";
import { OCRParseResult, OCRItem } from "./use-ocr";

interface OcrReviewModalProps {
  ocrData: OCRParseResult;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (data: {
    customerName: string;
    customerPhone: string;
    amount: string;
    lines: Array<{
      description: string;
      quantity: number;
      unit_price: string;
    }>;
  }) => void;
  isCreating?: boolean;
}

export function OcrReviewModal({
  ocrData,
  isOpen,
  onClose,
  onConfirm,
  isCreating = false,
}: OcrReviewModalProps) {
  // Editable state
  const [customerName, setCustomerName] = useState(ocrData.customer_name);
  const [customerPhone, setCustomerPhone] = useState("");
  const [amount, setAmount] = useState(ocrData.amount);
  const [items, setItems] = useState<OCRItem[]>(ocrData.items);

  if (!isOpen) return null;

  const handleConfirm = () => {
    onConfirm({
      customerName,
      customerPhone,
      amount,
      lines: items.map((item) => ({
        description: item.description,
        quantity: item.quantity,
        unit_price: item.unit_price,
      })),
    });
  };

  const handleItemChange = (
    index: number,
    field: keyof OCRItem,
    value: string | number
  ) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const handleAddItem = () => {
    setItems([
      ...items,
      { description: "", quantity: 1, unit_price: "0" },
    ]);
  };

  const handleRemoveItem = (index: number) => {
    setItems(items.filter((_, i) => i !== index));
  };

  // Confidence indicator
  const confidenceColors = {
    high: "bg-green-100 text-green-800 border-green-200",
    medium: "bg-yellow-100 text-yellow-800 border-yellow-200",
    low: "bg-red-100 text-red-800 border-red-200",
  };

  const confidenceIcons = {
    high: "✓",
    medium: "⚠",
    low: "⚠",
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="sticky top-0 border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-slate-900">
                Review Extracted Data
              </h2>
              <p className="text-sm text-slate-500">
                Check and edit the information before creating invoice
              </p>
            </div>

            {/* Confidence badge */}
            <div
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                confidenceColors[ocrData.confidence]
              }`}
            >
              {confidenceIcons[ocrData.confidence]} {ocrData.confidence.toUpperCase()} CONFIDENCE
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="space-y-6 px-6 py-6">
          {/* Warning for low confidence */}
          {ocrData.confidence === "low" && (
            <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
              <div className="flex items-start space-x-3">
                <svg
                  className="mt-0.5 h-5 w-5 flex-shrink-0 text-yellow-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                  />
                </svg>
                <div>
                  <p className="text-sm font-medium text-yellow-800">
                    Low Confidence - Please Review Carefully
                  </p>
                  <p className="mt-1 text-xs text-yellow-700">
                    The image quality may be poor. Verify all amounts and details before proceeding.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Customer Information */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">
              Customer Information
            </h3>

            <div>
              <label
                htmlFor="customerName"
                className="block text-sm font-medium text-slate-700"
              >
                Customer Name *
              </label>
              <input
                id="customerName"
                type="text"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                required
              />
            </div>

            <div>
              <label
                htmlFor="customerPhone"
                className="block text-sm font-medium text-slate-700"
              >
                Customer Phone (Optional)
              </label>
              <input
                id="customerPhone"
                type="tel"
                value={customerPhone}
                onChange={(e) => setCustomerPhone(e.target.value)}
                placeholder="+234XXXXXXXXXX"
                className="mt-1 block w-full rounded-lg border border-slate-300 px-4 py-2 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-slate-500">
                Include for automatic WhatsApp delivery
              </p>
            </div>
          </div>

          {/* Invoice Items */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900">
                Invoice Items
              </h3>
              <button
                type="button"
                onClick={handleAddItem}
                className="text-sm font-medium text-blue-600 hover:text-blue-700"
              >
                + Add Item
              </button>
            </div>

            <div className="space-y-3">
              {items.map((item, index) => (
                <div
                  key={index}
                  className="grid grid-cols-12 gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3"
                >
                  {/* Description */}
                  <div className="col-span-12 sm:col-span-6">
                    <input
                      type="text"
                      value={item.description}
                      onChange={(e) =>
                        handleItemChange(index, "description", e.target.value)
                      }
                      placeholder="Item description"
                      className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Quantity */}
                  <div className="col-span-5 sm:col-span-2">
                    <input
                      type="number"
                      value={item.quantity}
                      onChange={(e) =>
                        handleItemChange(index, "quantity", parseInt(e.target.value) || 1)
                      }
                      min="1"
                      className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Unit Price */}
                  <div className="col-span-5 sm:col-span-3">
                    <input
                      type="text"
                      value={item.unit_price}
                      onChange={(e) =>
                        handleItemChange(index, "unit_price", e.target.value)
                      }
                      placeholder="Price"
                      className="w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>

                  {/* Remove button */}
                  <div className="col-span-2 sm:col-span-1 flex items-center">
                    <button
                      type="button"
                      onClick={() => handleRemoveItem(index)}
                      className="text-red-600 hover:text-red-700"
                      title="Remove item"
                    >
                      <svg
                        className="h-5 w-5"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Total Amount */}
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">
              Total Amount
            </h3>

            <div>
              <label
                htmlFor="amount"
                className="block text-sm font-medium text-slate-700"
              >
                Amount (₦) *
              </label>
              <input
                id="amount"
                type="text"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-slate-300 px-4 py-2 text-lg font-semibold focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                required
              />
            </div>
          </div>

          {/* Raw extracted text (collapsible) */}
          {ocrData.raw_text && (
            <details className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <summary className="cursor-pointer text-sm font-medium text-slate-700">
                View Raw Extracted Text
              </summary>
              <pre className="mt-2 whitespace-pre-wrap text-xs text-slate-600">
                {ocrData.raw_text}
              </pre>
            </details>
          )}
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 flex items-center justify-end space-x-3 border-t border-slate-200 bg-slate-50 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            disabled={isCreating}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={isCreating || !customerName || !amount}
            className="rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isCreating ? (
              <span className="flex items-center space-x-2">
                <svg
                  className="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <span>Creating...</span>
              </span>
            ) : (
              "Create Invoice"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
