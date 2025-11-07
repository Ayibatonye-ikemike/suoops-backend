"use client";

import { RegisterForm } from "@/features/auth/register-form";
import RegulatoryNotice from "@/components/regulatory-notice";

export default function RegisterPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-green-600 to-emerald-700 p-8">
      <div className="flex w-full max-w-lg flex-col gap-6">
        <RegisterForm />
        <RegulatoryNotice variant="general" />
      </div>
    </main>
  );
}
