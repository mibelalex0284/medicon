"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { authService } from "@/services/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Lock,
  ShieldAlert,
  ShieldCheck,
  User,
  UserPlus,
} from "lucide-react";

export default function RegisterPage() {
  const router = useRouter();
  const { registerPatient } = useAuth();

  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isRegistrationEnabled, setIsRegistrationEnabled] = useState(false);

  // Form fields
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phone, setPhone] = useState("");
  const [emergencyContact, setEmergencyContact] = useState("");
  const [preferredLanguage, setPreferredLanguage] = useState("en");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    authService
      .getRegistrationStatus()
      .then((status) => {
        if (isMounted) {
          setIsRegistrationEnabled(status.patient_self_registration_enabled);
          setIsLoadingStatus(false);
        }
      })
      .catch(() => {
        if (isMounted) {
          setIsRegistrationEnabled(false);
          setIsLoadingStatus(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setSuccessMessage(null);

    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match. Please verify and re-enter your password.");
      return;
    }

    if (password.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }

    setIsSubmitting(true);
    try {
      await registerPatient({
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        date_of_birth: dateOfBirth,
        phone: phone.trim() || undefined,
        emergency_contact: emergencyContact.trim() || undefined,
        preferred_language: preferredLanguage,
      });

      setSuccessMessage("Your patient account has been created successfully!");
    } catch (err: any) {
      const msg = err.message || "Failed to create account. Please try again.";
      setErrorMessage(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoadingStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100/80 px-4 py-8">
        <div className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl p-8 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-sky-50 text-sky-600 animate-spin">
            <Activity size={24} />
          </div>
          <h2 className="text-sm font-bold text-slate-800">
            Checking Registration Availability...
          </h2>
          <p className="text-xs text-slate-500">
            Verifying clinic administrative policies with outpatient services.
          </p>
        </div>
      </div>
    );
  }

  // State: Public Registration Disabled
  if (!isRegistrationEnabled) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100/80 px-4 py-8">
        <div
          data-testid="registration-disabled-view"
          className="w-full max-w-md bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden animate-in fade-in duration-200"
        >
          {/* Header Banner */}
          <div className="bg-slate-900 px-6 py-6 text-white border-b border-slate-800">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-amber-600 rounded-lg text-white">
                <ShieldAlert size={22} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-amber-400">
                  CareRoute-X Security Policy
                </span>
                <h1 className="text-xl font-bold text-white tracking-tight">
                  Registration Unavailable
                </h1>
              </div>
            </div>
          </div>

          <div className="p-6 md:p-8 space-y-6">
            <div className="p-4 bg-amber-50 border border-amber-200 rounded-xl space-y-2">
              <h2 className="text-sm font-bold text-amber-900 flex items-center gap-2">
                <ShieldAlert size={16} className="text-amber-600 shrink-0" />
                Public Patient Registration is Currently Closed
              </h2>
              <p className="text-xs text-amber-800 leading-relaxed">
                Clinic administration has temporarily paused new public self-registration.
                If you already have a patient account or require clinical assistance, please sign in
                or contact the clinic reception desk.
              </p>
            </div>

            <div className="space-y-3">
              <Link href="/login" className="w-full block">
                <Button
                  id="return-to-login-btn"
                  data-testid="return-to-login-btn"
                  size="lg"
                  className="w-full flex items-center justify-center gap-2 bg-sky-700 hover:bg-sky-800 font-semibold"
                >
                  <ArrowLeft size={16} />
                  Return to Sign In
                </Button>
              </Link>
            </div>
          </div>

          <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 text-center">
            <p className="text-[11px] text-slate-400">
              CareRoute-X Outpatient Care Navigation · HIPAA/GDPR Compliant
            </p>
          </div>
        </div>
      </div>
    );
  }

  // State: Public Registration Enabled
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100/80 px-4 py-8">
      <div
        data-testid="registration-form-view"
        className="w-full max-w-lg bg-white rounded-2xl border border-slate-200 shadow-xl overflow-hidden animate-in fade-in duration-200"
      >
        {/* Top Header */}
        <div className="bg-slate-900 px-6 py-6 text-white border-b border-slate-800">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-sky-600 rounded-lg text-white">
                <UserPlus size={22} className="stroke-[2.5]" />
              </div>
              <div>
                <span className="text-xs font-bold uppercase tracking-widest text-sky-400">
                  CareRoute-X
                </span>
                <h1 className="text-xl font-bold text-white tracking-tight">
                  Create Patient Account
                </h1>
              </div>
            </div>
            <span className="inline-flex items-center gap-1 text-[11px] font-medium bg-slate-800 px-2.5 py-1 rounded-full text-slate-300 border border-slate-700">
              <ShieldCheck size={13} className="text-emerald-400" />
              Patient Role Only
            </span>
          </div>
        </div>

        <div className="p-6 md:p-8 space-y-6">
          {/* Info Notice: Strictly Patient Role */}
          <div className="p-3 bg-sky-50 border border-sky-200 rounded-xl flex items-start gap-2.5 text-xs text-sky-800">
            <ShieldCheck size={16} className="text-sky-600 shrink-0 mt-0.5" />
            <span className="leading-relaxed">
              Public self-registration is exclusively for patient outpatient access. Physician and
              administrative accounts cannot be created here and must be provisioned directly by
              clinic leadership.
            </span>
          </div>

          {/* Error Banner */}
          {errorMessage && (
            <div
              data-testid="registration-error-banner"
              className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-2.5 text-xs text-rose-700 animate-in fade-in duration-200"
            >
              <AlertCircle size={16} className="text-rose-500 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMessage}</span>
            </div>
          )}

          {/* Success Banner */}
          {successMessage && (
            <div
              data-testid="registration-success-banner"
              className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center gap-2.5 text-xs text-emerald-800 font-semibold animate-in fade-in"
            >
              <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Registration Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700">
                  Full Legal Name <span className="text-rose-500">*</span>
                </label>
                <Input
                  id="reg-full-name"
                  type="text"
                  required
                  placeholder="e.g. Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700">
                  Email Address <span className="text-rose-500">*</span>
                </label>
                <Input
                  id="reg-email"
                  type="email"
                  required
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700">
                  Password <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <Input
                    id="reg-password"
                    type="password"
                    required
                    placeholder="Min. 8 characters"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="text-sm pr-9"
                  />
                  <Lock size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700">
                  Confirm Password <span className="text-rose-500">*</span>
                </label>
                <div className="relative">
                  <Input
                    id="reg-confirm-password"
                    type="password"
                    required
                    placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="text-sm pr-9"
                  />
                  <Lock size={15} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700">
                  Date of Birth <span className="text-rose-500">*</span>
                </label>
                <Input
                  id="reg-dob"
                  type="date"
                  required
                  value={dateOfBirth}
                  onChange={(e) => setDateOfBirth(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5">
                <label className="block text-xs font-semibold text-slate-700">
                  Phone Number
                </label>
                <Input
                  id="reg-phone"
                  type="tel"
                  placeholder="+1 (555) 000-0000"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700">
                  Emergency Contact (Name & Phone)
                </label>
                <Input
                  id="reg-emergency"
                  type="text"
                  placeholder="e.g. John Doe (+1 555-0199)"
                  value={emergencyContact}
                  onChange={(e) => setEmergencyContact(e.target.value)}
                  className="text-sm"
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <label className="block text-xs font-semibold text-slate-700">
                  Preferred Language
                </label>
                <select
                  id="reg-language"
                  value={preferredLanguage}
                  onChange={(e) => setPreferredLanguage(e.target.value)}
                  className="w-full text-xs rounded-lg border border-slate-300 px-3 py-2 bg-white text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="en">English</option>
                  <option value="es">Español (Spanish)</option>
                  <option value="hi">हिन्दी (Hindi)</option>
                  <option value="fr">Français (French)</option>
                </select>
              </div>
            </div>

            <Button
              id="submit-register-btn"
              data-testid="submit-register-btn"
              type="submit"
              size="lg"
              className="w-full flex items-center justify-center gap-2 mt-4 bg-sky-700 hover:bg-sky-800 font-semibold"
              isLoading={isSubmitting}
            >
              Create Patient Account
              <ArrowRight size={16} />
            </Button>
          </form>

          <div className="pt-2 text-center border-t border-slate-200">
            <span className="text-xs text-slate-500">Already registered? </span>
            <Link
              href="/login"
              className="text-xs font-semibold text-sky-700 hover:text-sky-900 hover:underline"
            >
              Sign In to Care Portal
            </Link>
          </div>
        </div>

        <div className="bg-slate-50 px-6 py-3 border-t border-slate-200 text-center">
          <p className="text-[11px] text-slate-400">
            CareRoute-X Outpatient Care Navigation · Protected Health Information (PHI) Secure
          </p>
        </div>
      </div>
    </div>
  );
}
