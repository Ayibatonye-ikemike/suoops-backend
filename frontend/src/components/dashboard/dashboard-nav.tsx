"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLogout } from "@/features/auth/use-auth-session";

const navItems = [
  { href: "/dashboard", label: "Invoices", icon: "📄" },
  { href: "/dashboard/tax", label: "Tax Compliance", icon: "💼" },
  { href: "/dashboard/vat", label: "VAT", icon: "📊" },
  { href: "/dashboard/settings", label: "Settings", icon: "⚙️" },
];

export function DashboardNav() {
  const pathname = usePathname();
  const logout = useLogout();

  const handleLogout = () => {
    logout();
  };

  return (
    <nav className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-8 py-4">
        <div className="flex items-center gap-8">
                    <span className="text-xl font-bold text-slate-900">
            SuoOps
          </span>
          <div className="flex gap-2">
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-brand-primary text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <span>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
        >
          Logout
        </button>
      </div>
    </nav>
  );
}
