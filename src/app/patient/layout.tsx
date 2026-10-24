"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  Home,
  Search,
  Calendar,
  Clock,
  BookOpen,
  User,
  Activity,
  LogOut,
  Stethoscope,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { EMERGENCY_CONTACT } from "@/lib/constants";

const NAV_ITEMS = [
  { label: "Home", href: "/patient/dashboard", icon: Home },
  { label: "Find Care", href: "/patient/find-care", icon: Search },
  { label: "Appointments", href: "/patient/appointments", icon: Calendar },
  { label: "Queue", href: "/patient/queue", icon: Clock },
  { label: "Health", href: "/patient/health", icon: BookOpen },
  { label: "Profile", href: "/patient/profile", icon: User },
];

export default function PatientLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user, isLoading, logout, loginAsRole } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        router.replace("/login");
      } else if (user.role === "unregistered") {
        router.replace("/account-setup");
      } else if (user.role !== "patient") {
        if (user.role === "doctor") router.replace("/doctor/dashboard");
        else if (user.role === "admin") router.replace("/admin/dashboard");
        else router.replace("/login");
      }
    }
  }, [user, isLoading, router]);

  if (isLoading || !user || user.role !== "patient") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-3 border-sky-600 border-t-transparent" />
          <p className="text-xs text-slate-500 font-medium tracking-wide">
            Verifying patient workspace access...
          </p>
        </div>
      </div>
    );
  }

  const initials = (user.name || user.email || "PT")
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col md:flex-row pb-20 md:pb-0">
      {/* Desktop Compact Sidebar (hidden on mobile) */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 bg-white border-r border-slate-200 z-30">
        <div className="flex flex-col h-full">
          {/* Brand Header */}
          <div className="p-5 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-sky-600 rounded-lg text-white">
                <Activity size={20} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-sky-600 block">
                  CareRoute-X
                </span>
                <span className="text-base font-bold text-slate-900 tracking-tight">
                  Patient Portal
                </span>
              </div>
            </div>
          </div>

          {/* Patient Badge */}
          <div className="px-5 py-3.5 bg-slate-50 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-full bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-sm">
                {initials}
              </div>
              <div className="overflow-hidden">
                <p className="text-sm font-semibold text-slate-800 truncate">
                  {user.name || user.email || "Patient"}
                </p>
                <p className="text-[11px] text-slate-500 font-mono">
                  {user.email}
                </p>
              </div>
            </div>
          </div>

          {/* Navigation Items */}
          <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive =
                pathname === item.href ||
                (item.href !== "/patient/dashboard" &&
                  pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-sm font-medium transition-colors",
                    isActive
                      ? "bg-sky-50 text-sky-900 font-semibold"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  )}
                >
                  <Icon
                    size={18}
                    className={isActive ? "text-sky-600" : "text-slate-400"}
                  />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Switch Role / Emergency hotline / Sign Out */}
          <div className="p-4 border-t border-slate-100 space-y-2">
            <div className="p-2.5 rounded-lg bg-red-50 border border-red-100 text-red-900 text-xs">
              <div className="flex items-center gap-1.5 font-bold mb-0.5">
                <ShieldAlert size={14} className="text-red-700" />
                Emergency Hotline
              </div>
              <p className="text-[11px] text-red-700 leading-tight">
                Severe chest distress? Dial <strong>{EMERGENCY_CONTACT.primaryNumber}</strong> immediately.
              </p>
            </div>

            <div className="pt-2 flex items-center justify-between text-xs text-slate-500">
              {process.env.NODE_ENV === "development" && (
                <button
                  onClick={() => loginAsRole("doctor")}
                  className="hover:text-slate-900 hover:underline flex items-center gap-1"
                >
                  <Stethoscope size={13} />
                  Doctor View
                </button>
              )}
              <button
                onClick={logout}
                className="text-rose-600 hover:underline flex items-center gap-1"
              >
                <LogOut size={13} />
                Sign Out
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 md:pl-64 flex flex-col min-w-0">
        {/* Mobile Top Header (compact) */}
        <header className="sticky top-0 z-20 bg-white border-b border-slate-200 px-4 py-3 flex md:hidden items-center justify-between shadow-2xs">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-sky-600 rounded-md text-white">
              <Activity size={18} className="stroke-[2.5]" />
            </div>
            <div>
              <span className="text-[10px] font-bold uppercase tracking-wider text-sky-600 block leading-none">
                CareRoute-X
              </span>
              <span className="text-sm font-bold text-slate-900">
                Patient Care
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[11px] bg-slate-100 px-2 py-0.5 rounded-md font-mono text-slate-600">
              CRX-9281
            </span>
            <button
              onClick={logout}
              title="Sign Out"
              className="p-1.5 text-slate-400 hover:text-slate-700 rounded-md"
            >
              <LogOut size={16} />
            </button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 p-4 md:p-8 max-w-4xl w-full mx-auto">
          {children}
        </main>
      </div>

      {/* Mobile Bottom Navigation (compact, thumb-friendly 360-430px targets) */}
      <nav className="fixed bottom-0 inset-x-0 bg-white border-t border-slate-200 z-30 md:hidden flex items-center justify-around px-1 py-1.5 shadow-lg safe-area-inset-bottom">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const isActive =
            pathname === item.href ||
            (item.href !== "/patient/dashboard" &&
              pathname.startsWith(item.href));
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex flex-col items-center justify-center py-1 px-2 rounded-lg text-[10px] font-medium transition-colors min-w-[54px]",
                isActive
                  ? "text-sky-600 font-semibold"
                  : "text-slate-500 hover:text-slate-900"
              )}
            >
              <Icon size={20} className={isActive ? "text-sky-600" : "text-slate-400"} />
              <span className="mt-0.5 tracking-tight">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
