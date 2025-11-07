/**
 * OCR Invoice Creation Page
 * Complete flow: Upload photo → Parse OCR → Review data → Create invoice
 */

"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { OcrPhotoUpload } from "@/features/invoices/ocr-photo-upload";
import { OcrReviewModal } from "@/features/invoices/ocr-review-modal";
import { useParseReceipt } from "@/features/invoices/use-ocr";
import { useCreateInvoice } from "@/features/invoices/use-create-invoice";
import Link from "next/link";
import { OCRParseResult } from "@/features/invoices/use-ocr";

export default function OcrInvoicePage() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [context, setContext] = useState<string>("");
  const [ocrData, setOcrData] = useState<OCRParseResult | null>(null);
  const [showReview, setShowReview] = useState(false);

  const parseReceipt = useParseReceipt();
  const createInvoice = useCreateInvoice();

  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setOcrData(null);
  };

  const handleProcess = async () => {
    if (!selectedFile) return;

    try {
      const result = await parseReceipt.mutateAsync({
        file: selectedFile,
        context: context || undefined,
      });

      setOcrData(result);
      setShowReview(true);
    } catch (error) {
      // Narrow known error shape (AxiosError-like) for logging without using `any`
      const message = (error as { message?: string })?.message || "Unknown error";
      console.error("OCR parsing failed:", message, error);
      // Error will be handled by the mutation error state with custom message
    }
  };

  // Check if error is a premium feature requirement
  const isPremiumFeatureError = Boolean(
    parseReceipt.error && (parseReceipt.error as { response?: { status?: number } })?.response?.status === 403
  );

  const handleConfirmInvoice = async (data: {
    customerName: string;
    customerPhone: string;
    amount: string;
    lines: Array<{
      description: string;
      quantity: number;
      unit_price: string;
    }>;
  }) => {
    try {
      const invoice = await createInvoice.mutateAsync({
        customer_name: data.customerName,
        customer_phone: data.customerPhone || undefined,
        amount: parseFloat(data.amount),
        lines: data.lines.map((line) => ({
          description: line.description,
          quantity: line.quantity,
          unit_price: parseFloat(line.unit_price),
        })),
      });

      // Success! Navigate to invoice detail
      router.push(`/dashboard/invoices/${invoice.invoice_id}`);
    } catch (error) {
      const message = (error as { message?: string })?.message || "Unknown error";
      console.error("Invoice creation failed:", message, error);
      // Error will be handled by the mutation error state
    }
  };

  const handleCloseReview = () => {
    setShowReview(false);
  };

  return (
    <div className="min-h-screen bg-slate-50 py-8">
      <div className="mx-auto max-w-4xl px-4">
        {/* Header */}
        <div className="mb-8">
          <div className="mb-4 flex items-center space-x-2 text-sm text-slate-600">
            <Link
              href="/dashboard/invoices"
              className="hover:text-blue-600"
            >
              Invoices
            </Link>
            <span>›</span>
            <span className="text-slate-900">Create from Photo</span>
          </div>

          <h1 className="text-3xl font-bold text-slate-900">
            📸 Create Invoice from Photo
          </h1>
          <p className="mt-2 text-slate-600">
            Upload a receipt or invoice photo, and we&apos;ll extract the details automatically
          </p>
        </div>

        {/* How it works */}
        <div className="mb-8 rounded-lg border border-blue-200 bg-blue-50 p-6">
          <h2 className="mb-3 text-lg font-semibold text-blue-900">
            🎯 How it works
          </h2>
          <ol className="space-y-2 text-sm text-blue-800">
            <li className="flex items-start space-x-2">
              <span className="font-bold">1.</span>
              <span>Take a photo or upload an existing receipt image</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="font-bold">2.</span>
              <span>AI extracts customer name, amount, and line items (5-10 seconds)</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="font-bold">3.</span>
              <span>Review and edit the extracted data if needed</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="font-bold">4.</span>
              <span>Confirm to create professional invoice instantly</span>
            </li>
          </ol>
        </div>

        {/* Main content */}
        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
          {/* Upload section */}
          <OcrPhotoUpload
            onFileSelect={handleFileSelect}
            onContextChange={setContext}
            isProcessing={parseReceipt.isPending}
          />

          {/* Process button */}
          {selectedFile && !parseReceipt.isPending && (
            <div className="mt-6">
              <button
                onClick={handleProcess}
                disabled={!selectedFile}
                className="w-full rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Process Photo with AI
              </button>
            </div>
          )}

          {/* Processing state */}
          {parseReceipt.isPending && (
            <div className="mt-6 rounded-lg border border-blue-200 bg-blue-50 p-6">
              <div className="flex items-center space-x-4">
                <svg
                  className="h-8 w-8 animate-spin text-blue-600"
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
                <div>
                  <p className="font-medium text-blue-900">
                    Processing your photo...
                  </p>
                  <p className="text-sm text-blue-700">
                    AI is reading the receipt and extracting invoice data
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Error state - Premium Feature Required */}
          {parseReceipt.isError && isPremiumFeatureError && (
            <div className="mt-6 rounded-lg border-2 border-yellow-300 bg-gradient-to-r from-yellow-50 to-orange-50 p-6">
              <div className="flex items-start space-x-3">
                <svg
                  className="mt-0.5 h-6 w-6 flex-shrink-0 text-yellow-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                <div className="flex-1">
                  <p className="text-lg font-bold text-yellow-900">
                    🔒 Premium Feature Required
                  </p>
                  <p className="mt-2 text-sm text-yellow-800">
                    Photo invoice OCR is only available on paid subscription plans.
                  </p>
                  <div className="mt-4 rounded-lg bg-white/60 p-4">
                    <p className="text-sm font-semibold text-slate-900 mb-2">
                      ✨ Upgrade to unlock:
                    </p>
                    <ul className="space-y-1 text-sm text-slate-700">
                      <li>📸 Photo invoice OCR</li>
                      <li>🎙️ Voice message invoices</li>
                      <li>🎨 Custom branding with your logo</li>
                      <li>📊 More monthly invoices</li>
                      <li>💬 Priority support</li>
                    </ul>
                  </div>
                  <div className="mt-4 flex gap-3">
                    <Link
                      href="/dashboard/subscription"
                      className="inline-flex items-center rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 px-6 py-2.5 text-sm font-semibold text-white shadow-md hover:from-blue-700 hover:to-purple-700 transition-all"
                    >
                      🚀 Upgrade Now
                    </Link>
                    <Link
                      href="/dashboard/invoices"
                      className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-6 py-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-all"
                    >
                      ← Back to Invoices
                    </Link>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Error state - Other Errors */}
          {parseReceipt.isError && !isPremiumFeatureError && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
              <div className="flex items-start space-x-3">
                <svg
                  className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <p className="font-medium text-red-900">
                    Failed to process photo
                  </p>
                  <p className="mt-1 text-sm text-red-700">
                    {parseReceipt.error?.message || "Please try again with a clearer image"}
                  </p>
                  <button
                    onClick={handleProcess}
                    className="mt-3 text-sm font-medium text-red-600 hover:text-red-700"
                  >
                    Try Again
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Invoice creation error */}
          {createInvoice.isError && (
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
              <div className="flex items-start space-x-3">
                <svg
                  className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <p className="font-medium text-red-900">
                    Failed to create invoice
                  </p>
                  <p className="mt-1 text-sm text-red-700">
                    {createInvoice.error?.message || "Please try again"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Tips section */}
        <div className="mt-8 rounded-lg border border-slate-200 bg-white p-6">
          <h3 className="mb-3 text-lg font-semibold text-slate-900">
            💡 Tips for Best Results
          </h3>
          <ul className="space-y-2 text-sm text-slate-600">
            <li className="flex items-start space-x-2">
              <span className="text-green-600">✓</span>
              <span>Use good lighting - natural light works best</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-600">✓</span>
              <span>Keep receipt flat and in focus</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-600">✓</span>
              <span>Ensure all text is clearly visible</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-green-600">✓</span>
              <span>Works best with printed receipts (handwritten may vary)</span>
            </li>
            <li className="flex items-start space-x-2">
              <span className="text-red-600">✗</span>
              <span>Avoid shadows, glare, or blurry images</span>
            </li>
          </ul>

          <div className="mt-4 rounded-lg bg-blue-50 border border-blue-200 p-4">
            <p className="text-xs text-blue-800">
              <strong>🔒 Premium Feature:</strong> Photo invoice OCR requires a paid subscription plan. <strong>Speed:</strong> 5-10 seconds • <strong>Accuracy:</strong> 85-95% for clear images
            </p>
          </div>
        </div>
      </div>

      {/* Review Modal */}
      {ocrData && (
        <OcrReviewModal
          ocrData={ocrData}
          isOpen={showReview}
          onClose={handleCloseReview}
          onConfirm={handleConfirmInvoice}
          isCreating={createInvoice.isPending}
        />
      )}
    </div>
  );
}
