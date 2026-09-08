"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  Stethoscope,
  LayoutDashboard,
  Users,
  ClipboardCheck,
  Calendar,
  BarChart2,
  User,
  LogOut,
  Activity,
  Building2,
  ArrowRightLeft,
} from "lucide-react";
import { cn } from "@/lib/utils";

const DOCTOR_NAV = [
  { label: "Overview", href: "/doctor/dashboard", icon: LayoutDashboard },
  { label: "Live Queue", href: "/doctor/queue", icon: Users },
  { label: "Active Consult", href: "/doctor/consultation", icon: ClipboardCheck },
  { label: "Appointments", href: "/doctor/appointments", icon: Calendar },
  { label: "Workload & Pace", href: "/doctor/workload", icon: BarChart2 },
  { label: "Profile", href: "/doctor/profile", icon: User },
];

export default function DoctorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { logout, loginAsRole } = useAuth();

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col md:flex-row">
      {/* Desktop Doctor Clinical Workspace Sidebar (1024px+) */}
      <aside className="hidden md:flex md:w-64 md:flex-col md:fixed md:inset-y-0 bg-slate-900 text-white z-30 shadow-xl">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="p-5 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-teal-600 rounded-lg text-white">
                <Stethoscope size={20} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-teal-400 block">
                  CareRoute-X
                </span>
                <span className="text-base font-bold text-white tracking-tight">
                  Clinical Workspace
                </span>
              </div>
            </div>
          </div>

          {/* Doctor Info Badge */}
          <div className="px-5 py-4 bg-slate-950/60 border-b border-slate-800/80">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-teal-500/20 text-teal-400 border border-teal-500/30 flex items-center justify-center font-bold text-sm">
                AM
              </div>
              <div className="overflow-hidden">
                <p className="text-sm font-semibold text-white truncate">
                  Dr. Anita Menon, MD
                </p>
                <p className="text-[11px] text-teal-300 font-mono">
                  Room 204 · Adult OPD
                </p>
              </div>
            </div>
            <div className="mt-2.5 flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-[11px] text-slate-300 font-medium">
                Clinic Queue Active (Room 204)
              </span>
            </div>
          </div>

          {/* Nav Items */}
          <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
            {DOCTOR_NAV.map((item) => {
              const Icon = item.icon;
              const isActive =
                pathname === item.href ||
                (item.href !== "/doctor/dashboard" &&
                  pathname.startsWith(item.href));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-semibold tracking-wide transition-colors",
                    isActive
                      ? "bg-teal-600 text-white shadow-xs"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  )}
                >
                  <Icon
                    size={17}
                    className={isActive ? "text-white" : "text-slate-400"}
                  />
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Role switcher & Logout */}
          <div className="p-4 border-t border-slate-800 space-y-2 text-xs">
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <button
                onClick={() => loginAsRole("patient")}
                className="py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center gap-1"
              >
                <Activity size={12} />
                Patient
              </button>
              <button
                onClick={() => loginAsRole("admin")}
                className="py-1.5 px-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center justify-center gap-1"
              >
                <Building2 size={12} />
                Admin
              </button>
            </div>

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

      {/* Main Surface */}
      <div className="flex-1 md:pl-64 flex flex-col min-w-0">
        {/* Mobile Header */}
        <header className="sticky top-0 z-20 bg-slate-900 text-white px-4 py-3 flex md:hidden items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="p-1.5 bg-teal-600 rounded-md text-white">
              <Stethoscope size={18} />
            </div>
            <span className="text-sm font-bold">Dr. Menon · Room 204</span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/doctor/queue"
              className="text-xs bg-teal-600 px-2.5 py-1 rounded-md font-medium text-white"
            >
              Queue
            </Link>
            <button onClick={logout} className="text-slate-400 p-1">
              <LogOut size={16} />
            </button>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 p-4 md:p-8 max-w-6xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
