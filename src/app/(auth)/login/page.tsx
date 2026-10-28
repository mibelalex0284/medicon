"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isSupabaseConfigured } from "@/lib/supabase/client";
import { authService } from "@/services/auth";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Eye,
  EyeOff,
  Mail,
  ShieldCheck,
  UserPlus,
} from "lucide-react";

export default function LoginPage() {
  const { loginWithCredentials } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);
    try {
      await loginWithCredentials(email.trim(), password);
    } catch (err: any) {
      setErrorMessage(
        err.message || "Authentication failed. Please check your credentials and try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100/80 px-4 py-8">
      <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200/90 shadow-xl overflow-hidden">
        {/* Top Header */}
        <div className="bg-slate-900 px-6 py-6 text-white border-b border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-sky-600 rounded-lg text-white">
                <Activity size={22} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-sky-400">
                  MediLink
                </span>
                <h1 className="text-xl font-bold text-white tracking-tight">
                  Outpatient Platform
                </h1>
              </div>
            </div>

          </div>
        </div>

        <div className="p-6 md:p-8 space-y-6">
          {/* Welcome back heading & subtitle */}
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-slate-900 tracking-tight">
              Welcome back
            </h2>
            <p className="text-sm text-slate-500">
              Sign in to your MediLink account.
            </p>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-2.5 text-xs text-rose-700 animate-in fade-in duration-200">
              <AlertCircle size={16} className="text-rose-500 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMessage}</span>
            </div>
          )}

          {/* Unified Login Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="login-email"
                className="block text-xs font-semibold text-slate-700"
              >
                Email address
              </label>
              <div className="relative">
                <Input
                  id="login-email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="text-sm pr-9"
                />
                <Mail
                  size={15}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="login-password"
                className="block text-xs font-semibold text-slate-700"
              >
                Password
              </label>
              <div className="relative">
                <Input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  placeholder="••••••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="text-sm pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 focus:outline-none transition-colors"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff size={16} />
                  ) : (
                    <Eye size={16} />
                  )}
                </button>
              </div>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full flex items-center justify-center gap-2 mt-2 bg-sky-700 hover:bg-sky-800 font-semibold"
              isLoading={isSubmitting}
            >
              <span>Sign In</span>
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
        </div>

        <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 text-center">
          <p className="text-[11px] text-slate-400">
            MediLink Outpatient Care Navigation
          </p>
        </div>
      </div>
    </div>
  );
}
