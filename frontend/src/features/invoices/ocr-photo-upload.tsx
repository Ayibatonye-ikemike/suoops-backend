/**
 * OCR Photo Upload Component
 * Allows users to upload receipt/invoice photos for OCR processing
 */

"use client";

import { useState, useRef } from "react";
import Image from "next/image";

interface OcrPhotoUploadProps {
  onFileSelect: (file: File) => void;
  onContextChange?: (context: string) => void;
  isProcessing?: boolean;
}

export function OcrPhotoUpload({
  onFileSelect,
  onContextChange,
  isProcessing = false,
}: OcrPhotoUploadProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [context, setContext] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Allowed file types
  const ALLOWED_TYPES = [
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/gif",
  ];
  const MAX_SIZE_MB = 10;
  const MAX_SIZE_BYTES = MAX_SIZE_MB * 1024 * 1024;

  const validateFile = (file: File): string | null => {
    // Check file type
    if (!ALLOWED_TYPES.includes(file.type)) {
      return "Invalid file type. Please upload JPEG, PNG, WebP, BMP, or GIF image.";
    }

    // Check file size
    if (file.size > MAX_SIZE_BYTES) {
      return `File too large. Maximum size is ${MAX_SIZE_MB}MB.`;
    }

    // Check if file is empty
    if (file.size === 0) {
      return "File is empty. Please select a valid image.";
    }

    return null;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Validate file
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      setPreview(null);
      setFileName("");
      return;
    }

    // Clear error and set preview
    setError("");
    setFileName(file.name);

    // Create preview
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreview(reader.result as string);
    };
    reader.readAsDataURL(file);

    // Notify parent
    onFileSelect(file);
  };

  const handleCameraClick = () => {
    if (fileInputRef.current) {
      // Set capture attribute for mobile camera
      fileInputRef.current.setAttribute("capture", "environment");
      fileInputRef.current.click();
    }
  };

  const handleUploadClick = () => {
    if (fileInputRef.current) {
      // Remove capture attribute for file picker
      fileInputRef.current.removeAttribute("capture");
      fileInputRef.current.click();
    }
  };

  const handleRemove = () => {
    setPreview(null);
    setFileName("");
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleContextChange = (value: string) => {
    setContext(value);
    onContextChange?.(value);
  };

  return (
    <div className="space-y-4">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        accept={ALLOWED_TYPES.join(",")}
        onChange={handleFileChange}
        className="hidden"
        disabled={isProcessing}
      />

      {/* Upload area */}
      {!preview ? (
        <div className="space-y-4">
          {/* Upload buttons */}
          <div className="grid grid-cols-2 gap-4">
            {/* Camera button (mobile) */}
            <button
              type="button"
              onClick={handleCameraClick}
              disabled={isProcessing}
              className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-8 transition-colors hover:border-blue-500 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg
                className="mb-3 h-12 w-12 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
              <span className="text-sm font-medium text-slate-700">
                Take Photo
              </span>
              <span className="mt-1 text-xs text-slate-500">
                Use camera
              </span>
            </button>

            {/* File picker button */}
            <button
              type="button"
              onClick={handleUploadClick}
              disabled={isProcessing}
              className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 p-8 transition-colors hover:border-blue-500 hover:bg-blue-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg
                className="mb-3 h-12 w-12 text-slate-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
              <span className="text-sm font-medium text-slate-700">
                Upload File
              </span>
              <span className="mt-1 text-xs text-slate-500">
                Choose from device
              </span>
            </button>
          </div>

          {/* File requirements */}
          <div className="rounded-lg bg-blue-50 p-4">
            <p className="text-sm font-medium text-blue-900">
              📸 Supported formats:
            </p>
            <p className="mt-1 text-xs text-blue-700">
              JPEG, PNG, WebP, BMP, GIF • Max 10MB • Clear, well-lit photos work best
            </p>
          </div>
        </div>
      ) : (
        /* Preview area */
        <div className="space-y-4">
          {/* Image preview */}
          <div className="relative overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
            <Image
              src={preview}
              alt="Receipt preview"
              width={400}
              height={300}
              className="mx-auto max-h-96 w-auto object-contain"
            />
          </div>

          {/* File info */}
          <div className="flex items-center justify-between rounded-lg bg-slate-50 p-4">
            <div className="flex items-center space-x-3">
              <svg
                className="h-8 w-8 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div>
                <p className="text-sm font-medium text-slate-900">{fileName}</p>
                <p className="text-xs text-slate-500">Ready to process</p>
              </div>
            </div>

            {/* Remove button */}
            <button
              type="button"
              onClick={handleRemove}
              disabled={isProcessing}
              className="rounded-lg px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Remove
            </button>
          </div>
        </div>
      )}

      {/* Context input (optional) */}
      {preview && (
        <div>
          <label
            htmlFor="context"
            className="block text-sm font-medium text-slate-700"
          >
            Business Context (Optional)
          </label>
          <input
            id="context"
            type="text"
            value={context}
            onChange={(e) => handleContextChange(e.target.value)}
            placeholder="e.g., hair salon, restaurant, retail store"
            disabled={isProcessing}
            className="mt-1 block w-full rounded-lg border border-slate-300 px-4 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500"
          />
          <p className="mt-1 text-xs text-slate-500">
            Helps improve accuracy for specific business types
          </p>
        </div>
      )}

      {/* Error message */}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}
    </div>
  );
}
