"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { AuthoritativeRole } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isSupabaseConfigured } from "@/lib/supabase/client";
import { authService } from "@/services/auth";
import {
  Activity,
  AlertCircle,
  Stethoscope,
  Building2,
  UserCheck,
  ShieldCheck,
  ArrowRight,
  Lock,
  UserPlus,
} from "lucide-react";

export default function LoginPage() {
  const { loginWithCredentials, loginAsRole } = useAuth();
  const [selectedRole, setSelectedRole] = useState<AuthoritativeRole>("patient");
  const [email, setEmail] = useState("sarah.jenkins@example.com");
  const [password, setPassword] = useState("••••••••••••");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSupabaseLive, setIsSupabaseLive] = useState(false);
  const [isRegistrationEnabled, setIsRegistrationEnabled] = useState(false);

  useEffect(() => {
    setIsSupabaseLive(isSupabaseConfigured());
    authService
      .getRegistrationStatus()
      .then((status) => {
        setIsRegistrationEnabled(status.patient_self_registration_enabled);
      })
      .catch(() => {
        setIsRegistrationEnabled(false);
      });
  }, []);

  const roleConfigs = {
    patient: {
      title: "Patient Portal",
      description: "Navigate symptoms, book clinical appointments, and track your live queue token.",
      defaultEmail: "sarah.jenkins@example.com",
      icon: Activity,
      badgeText: "Mobile-First Patient Experience",
      persona: "Sarah Jenkins (MRN: CRX-9281)",
    },
    doctor: {
      title: "Physician & Clinical Workspace",
      description: "Manage queue flow, patient triage intakes, and active doctor consultations.",
      defaultEmail: "dr.menon@careroute.org",
      icon: Stethoscope,
      badgeText: "Desktop-First Clinical Workspace",
      persona: "Dr. Anita Menon, MD (Internal Med / Room 204)",
    },
    admin: {
      title: "Clinic Operations & Administration",
      description: "Monitor multi-department queue bottlenecks, wait analytics, and scenario simulations.",
      defaultEmail: "ops.admin@careroute.org",
      icon: Building2,
      badgeText: "Enterprise Operational Oversight",
      persona: "Mark Evans (Clinic Operations Director)",
    },
  };

  const handleRoleSelect = (role: AuthoritativeRole) => {
    setSelectedRole(role);
    setEmail(roleConfigs[role].defaultEmail);
    setErrorMessage(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      await loginWithCredentials(email, password);
    } catch (err: any) {
      setErrorMessage(
        err.message || "Authentication failed. Please check your credentials and try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const ActiveIcon = roleConfigs[selectedRole].icon;

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100/80 px-4 py-8">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden">
        {/* Top Header */}
        <div className="bg-slate-900 px-6 py-6 text-white border-b border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-sky-600 rounded-lg text-white">
                <Activity size={22} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-sky-400">
                  CareRoute-X
                </span>
                <h1 className="text-xl font-bold text-white tracking-tight">
                  Outpatient Platform
                </h1>
              </div>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-slate-800 px-2.5 py-1 rounded-full text-slate-300 border border-slate-700">
              <ShieldCheck size={13} className={isSupabaseLive ? "text-emerald-400" : "text-amber-400"} />
              {isSupabaseLive ? "Supabase Auth" : "Dev Mock Auth"}
            </span>
          </div>
        </div>

        <div className="p-6 md:p-8 space-y-6">
          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-2.5 text-xs text-rose-700 animate-in fade-in duration-200">
              <AlertCircle size={16} className="text-rose-500 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMessage}</span>
            </div>
          )}

          {/* Role Tab Selector */}
          <div>
            <label className="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
              Select Workspace Role
            </label>
            <div className="grid grid-cols-3 gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200">
              {(["patient", "doctor", "admin"] as AuthoritativeRole[]).map((r) => {
                const Icon = roleConfigs[r].icon;
                const isSelected = selectedRole === r;
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => handleRoleSelect(r)}
                    className={`flex flex-col items-center justify-center py-2 px-1 rounded-lg text-xs font-semibold transition-all ${
                      isSelected
                        ? "bg-white text-slate-900 shadow-xs border border-slate-200/80"
                        : "text-slate-500 hover:text-slate-900"
                    }`}
                  >
                    <Icon size={16} className={isSelected ? "text-sky-600" : "text-slate-400"} />
                    <span className="capitalize mt-1">{r}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Role Card Overview */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ActiveIcon size={16} className="text-sky-600" />
                <h2 className="text-sm font-bold text-slate-900">
                  {roleConfigs[selectedRole].title}
                </h2>
              </div>
              <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-sky-100 text-sky-800">
                {roleConfigs[selectedRole].badgeText}
              </span>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              {roleConfigs[selectedRole].description}
            </p>
            <div className="pt-2 border-t border-slate-200/60 mt-2 flex items-center justify-between text-xs">
              <span className="text-slate-500">Sign in as:</span>
              <span className="font-semibold text-slate-800">
                {roleConfigs[selectedRole].persona}
              </span>
            </div>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Work Email or MRN
              </label>
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="text-sm"
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="block text-xs font-semibold text-slate-700">
                  Security Passcode
                </label>
                <span className="text-[11px] text-sky-600 hover:underline cursor-pointer">
                  Forgot?
                </span>
              </div>
              <div className="relative">
                <Input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="text-sm pr-9"
                />
                <Lock
                  size={15}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
                />
              </div>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full flex items-center justify-center gap-2 mt-2 bg-sky-700 hover:bg-sky-800 font-semibold"
              isLoading={isSubmitting}
            >
              Sign In to {selectedRole === "patient" ? "Care Portal" : `${selectedRole.toUpperCase()} Console`}
              <ArrowRight size={16} />
            </Button>

            {isRegistrationEnabled && (
              <div className="pt-2 text-center" data-testid="registration-enabled-container">
                <Link
                  href="/register"
                  id="create-patient-account-link"
                  data-testid="create-patient-account-link"
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-sky-700 hover:text-sky-900 hover:underline py-1 px-2 rounded-lg transition-colors"
                >
                  <UserPlus size={14} className="text-sky-600" />
                  <span>New patient? Create Patient Account</span>
                </Link>
              </div>
            )}
          </form>


          {/* Quick Demo Persona Switcher (Development Only) */}
          {process.env.NODE_ENV === "development" && (
            <div className="border-t border-slate-200 pt-4">
              <p className="text-[11px] text-slate-400 font-medium text-center uppercase tracking-wider mb-2.5">
                Development Rapid Workspace Switcher
              </p>
              <div className="grid grid-cols-3 gap-2">
                <button
                  type="button"
                  onClick={() => loginAsRole("patient")}
                  className="text-[11px] font-medium py-1.5 px-2 bg-slate-100 hover:bg-sky-50 hover:text-sky-700 text-slate-700 rounded-lg border border-slate-200 transition-colors text-center"
                >
                  Patient View
                </button>
                <button
                  type="button"
                  onClick={() => loginAsRole("doctor")}
                  className="text-[11px] font-medium py-1.5 px-2 bg-slate-100 hover:bg-teal-50 hover:text-teal-700 text-slate-700 rounded-lg border border-slate-200 transition-colors text-center"
                >
                  Doctor View
                </button>
                <button
                  type="button"
                  onClick={() => loginAsRole("admin")}
                  className="text-[11px] font-medium py-1.5 px-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg border border-slate-200 transition-colors text-center"
                >
                  Admin View
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 text-center">
          <p className="text-[11px] text-slate-400">
            CareRoute-X Outpatient Care Navigation · HIPAA/GDPR Architecture Ready
          </p>
        </div>
      </div>
    </div>
  );
}
