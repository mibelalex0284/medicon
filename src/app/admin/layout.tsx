"use client";

import React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import {
  Building2,
  LayoutDashboard,
  Layers,
  Calendar,
  BarChart3,
  Sliders,
  Settings,
  LogOut,
  Activity,
  Stethoscope,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

const ADMIN_NAV = [
  { label: "Dashboard", href: "/admin/dashboard", icon: LayoutDashboard },
  { label: "Department Queues", href: "/admin/queues", icon: Layers },
  { label: "Physicians", href: "/admin/doctors", icon: Stethoscope },
  { label: "Appointments", href: "/admin/appointments", icon: Calendar },
  { label: "Analytics", href: "/admin/analytics", icon: BarChart3 },
  { label: "Simulation Sandbox", href: "/admin/simulation", icon: Sliders },
  { label: "Settings", href: "/admin/settings", icon: Settings },
];

export default function AdminLayout({
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
      } else if (user.role !== "admin") {
        if (user.role === "patient") router.replace("/patient/dashboard");
        else if (user.role === "doctor") router.replace("/doctor/dashboard");
        else router.replace("/login");
      }
    }
  }, [user, isLoading, router]);

  if (isLoading || !user || user.role !== "admin") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 text-white">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-3 border-sky-500 border-t-transparent" />
          <p className="text-xs text-slate-400 font-medium tracking-wide">
            Verifying administrator authorization...
          </p>
        </div>
      </div>
    );
  }

  const adminName = user.name || user.email || "Clinic Administrator";
  const adminInitials = adminName
    .split(" ")
    .map((p) => p[0])
    .filter(Boolean)
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col md:flex-row">
      {/* Desktop Admin Operations Sidebar (1280px - 1440px+) */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 bg-slate-950 text-white z-30 shadow-2xl border-r border-slate-800">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="p-5 border-b border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-sky-600 rounded-lg text-white">
                <Building2 size={20} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-sky-400 block">
                  CareRoute-X
                </span>
                <span className="text-base font-bold text-white tracking-tight">
                  Clinic Operations
                </span>
              </div>
            </div>
          </div>

          {/* Admin User Badge */}
          <div className="px-5 py-3.5 bg-slate-900 border-b border-slate-800/60">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-xl bg-sky-500/20 text-sky-400 border border-sky-500/30 flex items-center justify-center font-bold text-xs">
                {adminInitials}
              </div>
              <div className="overflow-hidden">
                <p className="text-sm font-semibold text-white truncate">
                  {adminName}
                </p>
                <p className="text-[11px] text-slate-400 truncate font-mono">
                  {user.email}
                </p>
              </div>
            </div>
            <div className="mt-2 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400" />
              <span className="text-[11px] text-slate-300 font-mono">
                4 Clinics Active · 100% Operational
              </span>
            </div>
          </div>

          {/* Navigation */}
          <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
            {ADMIN_NAV.map((item) => {
              const Icon = item.icon;
              const isActive =
                pathname === item.href ||
                (item.href !== "/admin/dashboard" &&
                  pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-semibold tracking-wide transition-colors",
                    isActive
                      ? "bg-sky-600 text-white shadow-xs"
                      : "text-slate-400 hover:bg-slate-900 hover:text-white"
                  )}
                >
                  <Icon
                    size={16}
                    className={isActive ? "text-white" : "text-slate-500"}
                  />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Bottom Switcher & Sign Out */}
          <div className="p-4 border-t border-slate-800/80 space-y-2 text-xs">
            {process.env.NODE_ENV === "development" && (
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <button
                  onClick={() => loginAsRole("patient")}
                  className="py-1.5 px-2 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 flex items-center justify-center gap-1"
                >
                  <Activity size={12} />
                  Patient
                </button>
                <button
                  onClick={() => loginAsRole("doctor")}
                  className="py-1.5 px-2 rounded bg-slate-900 hover:bg-slate-800 text-slate-300 flex items-center justify-center gap-1"
                >
                  <Stethoscope size={12} />
                  Doctor
                </button>
              </div>
            )}

            <button
              onClick={logout}
              className="w-full py-1.5 px-2 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded flex items-center justify-center gap-1.5"
            >
              <LogOut size={13} />
              Sign Out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 md:pl-64 flex flex-col min-w-0">
        <main className="flex-1 p-5 md:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
