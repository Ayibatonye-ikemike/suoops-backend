"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/features/auth/auth-store";

function CallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const setTokens = useAuthStore((state) => state.setTokens);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(true);

  const ranRef = useRef(false);

  useEffect(() => {
    if (ranRef.current) {
      return; // guard against double invocation in strict mode / re-renders
    }
    ranRef.current = true;

    const handleOAuthCallback = async () => {
      try {
        const code = searchParams?.get("code");
        const state = searchParams?.get("state");
        const errorParam = searchParams?.get("error");

        console.log("[OAuth Callback] Starting with params:", { code: code?.substring(0, 20), state, error: errorParam });

        // Check for OAuth error from provider
        if (errorParam) {
          setError(errorParam === "access_denied" 
            ? "Sign in was cancelled. Please try again."
            : `Authentication failed: ${errorParam}`
          );
          setProcessing(false);
          return;
        }

        // Validate required parameters
        if (!code || !state) {
          console.error("[OAuth Callback] Missing required parameters");
          setError("Invalid OAuth callback. Missing required parameters.");
          setProcessing(false);
          return;
        }

        // Exchange code for tokens via backend
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://api.suoops.com';
        console.log("[OAuth Callback] Fetching tokens from:", apiUrl);
        
        const response = await fetch(
          `${apiUrl}/auth/oauth/google/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
          {
            method: "GET",
            headers: {
              "Content-Type": "application/json",
              Accept: "application/json",
            },
            credentials: "include",
          }
        );

        console.log("[OAuth Callback] Response status:", response.status);

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({ detail: "Authentication failed" }));
          console.error("[OAuth Callback] Failed:", errorData);
          throw new Error(errorData.detail || "Failed to complete sign in");
        }

        const data = await response.json();
        console.log("[OAuth Callback] Received tokens, access_expires_at:", data.access_expires_at);

        // Store tokens in auth store
        const accessExpiresAt: string =
          typeof data.access_expires_at === "string"
            ? data.access_expires_at
            : new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
        setTokens({
          accessToken: data.access_token,
          accessExpiresAt,
        });

        // Determine final post-auth destination.
        // If backend returned the callback URI itself (loop), fallback to /dashboard.
        // Support optional `next` query param on the callback URI for custom destination.
        const rawRedirect = data.redirect_uri || "/dashboard";
        let finalRedirect = rawRedirect;
        try {
          const urlObj = new URL(rawRedirect, window.location.origin);
          const nextParam = urlObj.searchParams.get("next");
          if (nextParam) {
            // Ensure it is a relative path to prevent open redirects.
            finalRedirect = nextParam.startsWith("/") ? nextParam : "/dashboard";
          } else if (urlObj.pathname.endsWith("/auth/callback")) {
            finalRedirect = "/dashboard";
          }
        } catch {
          if (rawRedirect.endsWith("/auth/callback")) {
            finalRedirect = "/dashboard";
          }
        }

        console.log("[OAuth Callback] Tokens stored, redirecting to:", finalRedirect);
        router.replace(finalRedirect);
      } catch (err) {
        console.error("[OAuth Callback] Error:", err);
        setError(err instanceof Error ? err.message : "An unexpected error occurred");
        setProcessing(false);
      }
    };

    if (searchParams) {
      void handleOAuthCallback();
    }
  }, [searchParams, router, setTokens]);

  if (processing) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-600 to-emerald-700">
        <div className="flex w-full max-w-md flex-col items-center gap-6 rounded-2xl bg-white p-10 shadow-xl">
          <div className="flex flex-col items-center gap-4">
            <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-green-600"></div>
            <div className="space-y-2 text-center">
              <h1 className="text-xl font-semibold text-slate-900">Completing sign in...</h1>
              <p className="text-sm text-slate-500">Please wait while we verify your account.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-600 to-emerald-700">
        <div className="flex w-full max-w-md flex-col gap-6 rounded-2xl bg-white p-10 shadow-xl">
          <div className="space-y-2 text-center">
            <h1 className="text-2xl font-semibold text-slate-900">Sign in failed</h1>
            <p className="text-sm text-slate-500">We couldn&apos;t complete your sign in.</p>
          </div>
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-600" role="alert">
            {error}
          </p>
          <button
            onClick={() => router.push("/login")}
            className="rounded-lg bg-green-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-green-700"
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return null;
}

export default function OAuthCallbackPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-600 to-emerald-700">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-white border-t-transparent"></div>
      </div>
    }>
      <CallbackContent />
    </Suspense>
  );
}
