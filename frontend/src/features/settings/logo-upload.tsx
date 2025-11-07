"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import Image from "next/image";
import { useState } from "react";

import { apiClient } from "@/api/client";
import type { components } from "@/api/types";

type CurrentUser = components["schemas"]["UserOut"];

const getErrorMessage = (err: unknown, fallback: string) => {
  if (isAxiosError(err)) {
    return err.response?.data?.detail || err.message || fallback;
  }
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === "string") {
    return err;
  }
  return fallback;
};

export function LogoUpload() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string>("");
  const queryClient = useQueryClient();

  const { data: user, isLoading, error: userError } = useQuery<CurrentUser>({
    queryKey: ["currentUser"],
    queryFn: async () => {
      const response = await apiClient.get<CurrentUser>("/users/me");
      return response.data;
    },
    retry: false,
    staleTime: 60000, // 1 minute
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const response = await apiClient.post("/users/me/logo", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      setSelectedFile(null);
      setPreviewUrl(null);
      setError("");
    },
    onError: (err: unknown) => {
      setError(getErrorMessage(err, "Failed to upload logo"));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      const response = await apiClient.delete("/users/me/logo");
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["currentUser"] });
      setSelectedFile(null);
      setPreviewUrl(null);
      setError("");
    },
    onError: (err: unknown) => {
      setError(getErrorMessage(err, "Failed to remove logo"));
    },
  });

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    const validTypes = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml"];
    if (!validTypes.includes(file.type)) {
      setError("Please select a PNG, JPG, JPEG, or SVG file");
      return;
    }

    // Validate file size (5MB)
    if (file.size > 5 * 1024 * 1024) {
      setError("File size must be less than 5MB");
      return;
    }

    setError("");
    setSelectedFile(file);

    const reader = new FileReader();
    reader.onload = (loadEvent) => {
      const result = loadEvent.target?.result;
      if (typeof result === "string") {
        setPreviewUrl(result);
      }
    };
    reader.readAsDataURL(file);
  };

  const handleUpload = () => {
    if (!selectedFile) return;
    uploadMutation.mutate(selectedFile);
  };

  const handleRemove = () => {
    if (
      typeof window === "undefined" ||
      window.confirm("Are you sure you want to remove your logo? It will no longer appear on invoices.")
    ) {
      deleteMutation.mutate();
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="animate-pulse space-y-4">
          <div className="h-32 w-32 rounded-lg bg-slate-200" />
          <div className="h-10 w-full rounded bg-slate-200" />
        </div>
      </div>
    );
  }

  if (userError || !user) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-500">Unable to load logo settings.</p>
      </div>
    );
  }

  const currentLogo = user?.logo_url;
  const displayLogo = previewUrl || currentLogo;

  return (
    <div className="space-y-4">
      {/* Current/Preview Logo */}
      {displayLogo && (
        <div className="flex items-center gap-4">
          <div className="relative h-24 w-24 overflow-hidden rounded-lg border border-slate-200 bg-white p-2">
            <Image
              src={displayLogo}
              alt="Business logo"
              fill
              sizes="96px"
              className="object-contain"
              unoptimized
            />
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-slate-700">
              {previewUrl ? "Preview" : "Current Logo"}
            </p>
            <p className="text-xs text-slate-500">
              This logo will appear on all your invoices and receipts
            </p>
          </div>
          {currentLogo && !previewUrl && (
            <button
              onClick={handleRemove}
              disabled={deleteMutation.isPending}
              className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {deleteMutation.isPending ? "Removing..." : "Remove"}
            </button>
          )}
        </div>
      )}

      {/* Upload Section */}
      {!currentLogo || previewUrl ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <label
              htmlFor="logo-upload"
              className="cursor-pointer rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              {previewUrl ? "Choose Different File" : "Choose File"}
            </label>
            <input
              id="logo-upload"
              type="file"
              accept="image/png,image/jpeg,image/jpg,image/svg+xml"
              onChange={handleFileSelect}
              className="hidden"
            />
            {selectedFile && (
              <span className="text-sm text-slate-600">{selectedFile.name}</span>
            )}
          </div>

          {previewUrl && (
            <div className="flex gap-2">
              <button
                onClick={handleUpload}
                disabled={uploadMutation.isPending}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploadMutation.isPending ? "Uploading..." : "Upload Logo"}
              </button>
              <button
                onClick={() => {
                  setSelectedFile(null);
                  setPreviewUrl(null);
                  setError("");
                }}
                className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
            </div>
          )}

          <p className="text-xs text-slate-500">
            Accepted formats: PNG, JPG, JPEG, SVG • Max size: 5MB • Recommended: Square logo,
            minimum 200x200px
          </p>
        </div>
      ) : (
        <label
          htmlFor="logo-upload-replace"
          className="inline-block cursor-pointer rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Replace Logo
          <input
            id="logo-upload-replace"
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/svg+xml"
            onChange={handleFileSelect}
            className="hidden"
          />
        </label>
      )}

      {/* Success Message */}
      {uploadMutation.isSuccess && (
        <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800">
          ✓ Logo uploaded successfully!
        </div>
      )}

      {deleteMutation.isSuccess && (
        <div className="rounded-lg bg-green-50 p-3 text-sm text-green-800">
          ✓ Logo removed successfully
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </div>
      )}
    </div>
  );
}
