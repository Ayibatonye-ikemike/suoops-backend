"use client";

import { Suspense } from "react";
import RegulatoryNotice from "@/components/regulatory-notice";
import { useSearchParams } from "next/navigation";

import { LoginForm } from "@/features/auth/login-form";

function LoginContent() {
  const searchParams = useSearchParams();
  const reason = searchParams?.get("reason");
  const registered = searchParams?.get("registered");
  
  let message: string | null = null;
  let messageType: "info" | "success" = "info";
  
  if (reason === "expired") {
    message = "Your session expired. Please sign in again.";
    messageType = "info";
  } else if (registered === "true") {
    message = "Account created successfully! Please sign in.";
    messageType = "success";
  }

  return (
    <>
      {message ? (
        <p
          className={
            messageType === "success"
              ? "rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
              : "rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700"
          }
          role="alert"
        >
          {message}
        </p>
      ) : null}
      <LoginForm />
    </>
  );
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-600 to-emerald-700 p-8">
      <div className="flex w-full max-w-lg flex-col gap-6">
        <Suspense fallback={<div>Loading...</div>}>
          <LoginContent />
        </Suspense>
        <RegulatoryNotice variant="general" className="mt-2" />
      </div>
    </main>
  );
}
