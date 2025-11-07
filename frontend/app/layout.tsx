import type { Metadata } from "next";
import "./globals.css";
import { ReactQueryProvider } from "@/lib/react-query-provider";
import { AuthProvider } from "@/features/auth/auth-provider";

export const metadata: Metadata = {
  title: "SuoOps Dashboard",
  description: "Create and send invoices for your business",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {/* Global provisional fiscalization disclaimer banner */}
        <div className="w-full bg-gradient-to-r from-blue-600 via-purple-600 to-blue-700 text-white text-xs sm:text-sm py-2 px-4 shadow-md">
          <p className="text-center font-medium">
            Fiscalization & external gateway validation are <span className="underline decoration-yellow-300 decoration-2 underline-offset-2">pending accreditation</span>. Current tax & compliance features generate provisional metadata only.
          </p>
        </div>
        <ReactQueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </ReactQueryProvider>
      </body>
    </html>
  );
}
