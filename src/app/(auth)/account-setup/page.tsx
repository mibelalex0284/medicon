"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { authService } from "@/services/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Activity,
  AlertTriangle,
  Building2,
  Stethoscope,
  UserCheck,
  RefreshCw,
  LogOut,
  ShieldCheck,
  ArrowRight,
  Clock,
  KeyRound,
  CheckCircle2,
  Lock,
  Eye,
  EyeOff,
  AlertCircle,
} from "lucide-react";

function AccountSetupContent() {
  const {
    user,
    isLoading,
    logout,
    refreshSession,
    completePatientProfile,
  } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();

  // Password Setup Mode State
  const [isPasswordMode, setIsPasswordMode] = useState(false);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmittingPassword, setIsSubmittingPassword] = useState(false);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  // Unregistered / Status check state
  const [isCheckingRole, setIsCheckingRole] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRegistrationEnabled, setIsRegistrationEnabled] = useState(true);
  const [showPatientForm, setShowPatientForm] = useState(false);

  // Patient profile completion form state
  const [fullName, setFullName] = useState("");
  const [dateOfBirth, setDateOfBirth] = useState("");
  const [phone, setPhone] = useState("");
  const [emergencyContact, setEmergencyContact] = useState("");
  const [preferredLanguage, setPreferredLanguage] = useState("en");
  const [isSubmittingProfile, setIsSubmittingProfile] = useState(false);

  // Detect whether the current request is for password setup / invitation activation
  useEffect(() => {
    const mode = searchParams?.get("mode");
    const type = searchParams?.get("type");
    const hasHashRecovery =
      typeof window !== "undefined" &&
      (window.location.hash.includes("type=recovery") ||
        window.location.hash.includes("type=invite"));

    if (
      mode === "set-password" ||
      type === "recovery" ||
      type === "invite" ||
      hasHashRecovery
    ) {
      setIsPasswordMode(true);
    }
  }, [searchParams]);

  // Standard auto-routing when NOT in password setup mode
  useEffect(() => {
    if (!isLoading && !isPasswordMode) {
      if (!user) {
        router.replace("/login");
      } else if (user.role === "patient") {
        router.replace("/patient/dashboard");
      } else if (user.role === "doctor") {
        router.replace("/doctor/dashboard");
      } else if (user.role === "admin") {
        router.replace("/admin/dashboard");
      }
    }
  }, [user, isLoading, isPasswordMode, router]);

  useEffect(() => {
    if (user?.name && user.name !== "User" && user.name !== user.email) {
      setFullName(user.name);
    }
    authService
      .getRegistrationStatus()
      .then((status) => {
        setIsRegistrationEnabled(status.patient_self_registration_enabled);
      })
      .catch(() => {
        setIsRegistrationEnabled(true);
      });
  }, [user]);

  // Handler for setting or updating account password (Physician Invitation / Password Setup)
  const handleSetPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (newPassword.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmittingPassword(true);
    try {
      await authService.updatePassword(newPassword);
      setPasswordSuccess(true);
      setStatusMessage("Password configured successfully! Activating session...");

      // Refresh authoritative session
      const refreshed = await refreshSession();
      const destRole = refreshed?.role || user?.role || "doctor";

      setTimeout(() => {
        if (destRole === "doctor") {
          router.replace("/doctor/dashboard");
        } else if (destRole === "admin") {
          router.replace("/admin/dashboard");
        } else if (destRole === "patient") {
          router.replace("/patient/dashboard");
        } else {
          router.replace("/doctor/dashboard");
        }
      }, 1500);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to set password";
      setErrorMessage(
        msg || "Failed to configure account password. Please try again or request a new invitation."
      );
    } finally {
      setIsSubmittingPassword(false);
    }
  };

  const handleCheckStatus = async () => {
    setIsCheckingRole(true);
    setStatusMessage(null);
    setErrorMessage(null);
    try {
      const refreshed = await refreshSession();
      if (!refreshed || refreshed.role === "unregistered") {
        setStatusMessage(
          "No active profile found yet. If an administrator recently provisioned your account, please allow a moment and try again."
        );
      } else {
        setStatusMessage(`Role successfully verified as '${refreshed.role}'. Redirecting...`);
        if (refreshed.role === "patient") router.push("/patient/dashboard");
        else if (refreshed.role === "doctor") router.push("/doctor/dashboard");
        else if (refreshed.role === "admin") router.push("/admin/dashboard");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to check account status";
      setErrorMessage(msg || "Failed to check account status with server.");
    } finally {
      setIsCheckingRole(false);
    }
  };

  const handleCompletePatientProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fullName.trim() || !dateOfBirth) {
      setErrorMessage("Full legal name and date of birth are required.");
      return;
    }

    setIsSubmittingProfile(true);
    setErrorMessage(null);
    try {
      await completePatientProfile({
        full_name: fullName.trim(),
        date_of_birth: dateOfBirth,
        phone: phone.trim() || undefined,
        emergency_contact: emergencyContact.trim() || undefined,
        preferred_language: preferredLanguage,
      });
      router.push("/patient/dashboard");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to complete patient registration";
      setErrorMessage(
        msg || "Failed to complete patient registration. Please try again."
      );
    } finally {
      setIsSubmittingProfile(false);
    }
  };

  // 1. Password Setup View (For invited physicians or password reset)
  if (isPasswordMode) {
    return (
      <div className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="flex items-center justify-center gap-2.5 mb-4">
            <div className="p-2.5 bg-sky-600 rounded-xl text-white shadow-md">
              <KeyRound size={26} className="stroke-[2.5]" />
            </div>
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-sky-600 block">
                CareRoute-X Security
              </span>
              <span className="text-xl font-bold text-slate-900 tracking-tight">
                Account Activation
              </span>
            </div>
          </div>
        </div>

        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <div className="bg-white py-8 px-6 shadow-xl rounded-2xl border border-slate-200 sm:px-10 space-y-6">
            <div className="text-center space-y-1">
              <h2 className="text-lg font-bold text-slate-900">
                Set Your Confidential Password
              </h2>
              <p className="text-xs text-slate-500">
                Establish a secure password to activate your clinical workspace credentials.
              </p>
            </div>

            {/* Account Details if loaded */}
            {user && (
              <div className="bg-slate-50 rounded-xl p-3 border border-slate-200 text-xs space-y-1.5">
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Account:</span>
                  <span className="font-semibold text-slate-900">{user.email}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-slate-500">Designated Role:</span>
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-100 text-sky-800 capitalize">
                    {user.role}
                  </span>
                </div>
              </div>
            )}

            {passwordSuccess ? (
              <div
                id="password-setup-success"
                data-testid="password-setup-success"
                className="rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-center space-y-2 animate-in fade-in"
              >
                <div className="inline-flex p-2 bg-emerald-100 text-emerald-700 rounded-full">
                  <CheckCircle2 size={24} />
                </div>
                <h3 className="text-sm font-bold text-emerald-900">
                  Password Configured Successfully!
                </h3>
                <p className="text-xs text-emerald-700">
                  Your credentials have been securely activated. Redirecting you to your workspace...
                </p>
                <div className="flex justify-center pt-2">
                  <RefreshCw size={16} className="animate-spin text-emerald-600" />
                </div>
              </div>
            ) : (
              <form onSubmit={handleSetPassword} className="space-y-4">
                {errorMessage && (
                  <div
                    id="password-setup-error"
                    data-testid="password-setup-error"
                    className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-xs text-rose-700 flex items-start gap-2"
                  >
                    <AlertCircle size={15} className="shrink-0 mt-0.5 text-rose-600" />
                    <span>{errorMessage}</span>
                  </div>
                )}

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    New Password <span className="text-rose-500">*</span>
                  </label>
                  <div className="relative">
                    <Input
                      id="account-setup-new-password"
                      data-testid="account-setup-new-password"
                      type={showPassword ? "text" : "password"}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="At least 8 characters"
                      required
                      minLength={8}
                      className="pr-10 text-xs"
                      disabled={isSubmittingPassword}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                    >
                      {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Confirm Password <span className="text-rose-500">*</span>
                  </label>
                  <Input
                    id="account-setup-confirm-password"
                    data-testid="account-setup-confirm-password"
                    type={showPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="Re-enter your new password"
                    required
                    minLength={8}
                    className="text-xs"
                    disabled={isSubmittingPassword}
                  />
                </div>

                {/* Password strength checklist */}
                <div className="space-y-1 bg-slate-50 p-2.5 rounded-lg border border-slate-200 text-[11px] text-slate-500">
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`h-1.5 w-1.5 rounded-full ${
                        newPassword.length >= 8 ? "bg-emerald-500" : "bg-slate-300"
                      }`}
                    />
                    <span className={newPassword.length >= 8 ? "text-emerald-700 font-medium" : ""}>
                      At least 8 characters
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`h-1.5 w-1.5 rounded-full ${
                        newPassword && newPassword === confirmPassword
                          ? "bg-emerald-500"
                          : "bg-slate-300"
                      }`}
                    />
                    <span
                      className={
                        newPassword && newPassword === confirmPassword
                          ? "text-emerald-700 font-medium"
                          : ""
                      }
                    >
                      Passwords match
                    </span>
                  </div>
                </div>

                <Button
                  id="set-password-submit-btn"
                  data-testid="set-password-submit-btn"
                  type="submit"
                  disabled={isSubmittingPassword || !newPassword || !confirmPassword}
                  className="w-full bg-sky-700 hover:bg-sky-800 text-white text-xs font-semibold py-2 gap-2"
                >
                  {isSubmittingPassword ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Saving Password & Activating...
                    </>
                  ) : (
                    <>
                      <Lock size={14} />
                      Activate Account & Set Password
                    </>
                  )}
                </Button>
              </form>
            )}

            <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs">
              <button
                type="button"
                onClick={() => logout().then(() => router.replace("/login"))}
                className="text-slate-400 hover:text-slate-600 flex items-center gap-1"
              >
                <LogOut size={13} />
                Return to Login
              </button>
              <span className="text-[10px] text-slate-400 flex items-center gap-1">
                <ShieldCheck size={12} className="text-emerald-500" />
                End-to-End Encrypted
              </span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 2. Loading state when authenticating or checking role
  if (isLoading || !user || user.role !== "unregistered") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="flex flex-col items-center gap-3">
          <div className="h-9 w-9 animate-spin rounded-full border-3 border-sky-600 border-t-transparent" />
          <p className="text-xs text-slate-500 font-medium">Loading account details...</p>
        </div>
      </div>
    );
  }

  // 3. Unregistered User Role Resolution Interface
  return (
    <div className="min-h-screen bg-slate-100 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-xl">
        <div className="flex items-center justify-center gap-2.5 mb-4">
          <div className="p-2.5 bg-sky-600 rounded-xl text-white shadow-md">
            <Activity size={26} className="stroke-[2.5]" />
          </div>
          <div>
            <span className="text-xs font-bold uppercase tracking-wider text-sky-600 block">
              CareRoute-X
            </span>
            <span className="text-xl font-bold text-slate-900 tracking-tight">
              Account Provisioning Required
            </span>
          </div>
        </div>
      </div>

      <div className="sm:mx-auto sm:w-full sm:max-w-xl">
        <div className="bg-white py-8 px-6 shadow-xl rounded-2xl border border-slate-200 sm:px-10 space-y-6">
          {/* Identity Notice */}
          <div className="rounded-xl bg-amber-50 border border-amber-200 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
              <div className="text-sm">
                <h3 className="font-semibold text-amber-900">
                  Role Assignment Pending
                </h3>
                <p className="text-amber-800 text-xs mt-1 leading-relaxed">
                  You have successfully authenticated with{" "}
                  <strong className="font-semibold text-slate-900">{user.email}</strong>,
                  but your account has not yet been assigned an operational role (Patient, Doctor, or Clinic Administrator).
                </p>
              </div>
            </div>
          </div>

          {/* Account Details */}
          <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-xs space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-medium">Authenticated Email:</span>
              <span className="font-semibold text-slate-900">{user.email}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-medium">Auth User ID:</span>
              <span className="font-mono text-slate-700 text-[11px] truncate max-w-[240px]">
                {user.id}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-medium">Application Role:</span>
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-100 text-amber-800">
                unregistered
              </span>
            </div>
          </div>

          {statusMessage && (
            <div className="rounded-lg bg-sky-50 border border-sky-200 p-3.5 text-xs text-sky-800">
              {statusMessage}
            </div>
          )}

          {errorMessage && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 p-3.5 text-xs text-rose-700">
              {errorMessage}
            </div>
          )}

          {/* Role Pathways */}
          <div className="space-y-4 pt-2">
            {/* Pathway 1: Staff / Administrator / Physician */}
            <div className="border border-slate-200 rounded-xl p-4 bg-white hover:border-slate-300 transition-colors">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-slate-100 rounded-lg text-slate-700 shrink-0 mt-0.5">
                  <Building2 size={18} />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-slate-900">
                    Clinic Personnel & Administration
                  </h4>
                  <p className="text-xs text-slate-600 mt-1">
                    Physician and administrator roles are strictly provisioned by Clinic Operations. If your profile was recently registered by an administrator, click below to verify and enter your workspace.
                  </p>
                  <div className="mt-3">
                    <Button
                      onClick={handleCheckStatus}
                      disabled={isCheckingRole}
                      variant="outline"
                      size="sm"
                      className="border-slate-300 text-xs flex items-center gap-2"
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${isCheckingRole ? "animate-spin" : ""}`} />
                      {isCheckingRole ? "Checking Authorization..." : "Check Provisioning Status"}
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            {/* Pathway 2: Patient Registration */}
            <div className="border border-slate-200 rounded-xl p-4 bg-white hover:border-slate-300 transition-colors">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-sky-50 rounded-lg text-sky-700 shrink-0 mt-0.5">
                  <UserCheck size={18} />
                </div>
                <div className="flex-1">
                  <h4 className="text-sm font-semibold text-slate-900">
                    Patient Portal Registration
                  </h4>
                  {isRegistrationEnabled ? (
                    <>
                      <p className="text-xs text-slate-600 mt-1">
                        Are you an individual seeking clinical care? Complete your patient record to begin symptom triage, physician discovery, and appointment booking.
                      </p>
                      {!showPatientForm ? (
                        <div className="mt-3">
                          <Button
                            onClick={() => setShowPatientForm(true)}
                            size="sm"
                            className="bg-sky-700 hover:bg-sky-800 text-white text-xs flex items-center gap-2"
                          >
                            Complete Patient Profile
                            <ArrowRight size={14} />
                          </Button>
                        </div>
                      ) : (
                        <form
                          onSubmit={handleCompletePatientProfile}
                          className="mt-4 space-y-3 pt-3 border-t border-slate-200"
                        >
                          <div>
                            <label className="block text-xs font-semibold text-slate-700 mb-1">
                              Full Legal Name <span className="text-rose-500">*</span>
                            </label>
                            <Input
                              value={fullName}
                              onChange={(e) => setFullName(e.target.value)}
                              placeholder="e.g. John Doe"
                              required
                              className="text-xs"
                              disabled={isSubmittingProfile}
                            />
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className="block text-xs font-semibold text-slate-700 mb-1">
                                Date of Birth <span className="text-rose-500">*</span>
                              </label>
                              <Input
                                type="date"
                                value={dateOfBirth}
                                onChange={(e) => setDateOfBirth(e.target.value)}
                                required
                                className="text-xs"
                                disabled={isSubmittingProfile}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-semibold text-slate-700 mb-1">
                                Phone Number
                              </label>
                              <Input
                                type="tel"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                placeholder="+1 (555) 000-0000"
                                className="text-xs"
                                disabled={isSubmittingProfile}
                              />
                            </div>
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className="block text-xs font-semibold text-slate-700 mb-1">
                                Emergency Contact
                              </label>
                              <Input
                                value={emergencyContact}
                                onChange={(e) => setEmergencyContact(e.target.value)}
                                placeholder="Name & contact phone"
                                className="text-xs"
                                disabled={isSubmittingProfile}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-semibold text-slate-700 mb-1">
                                Preferred Language
                              </label>
                              <select
                                value={preferredLanguage}
                                onChange={(e) => setPreferredLanguage(e.target.value)}
                                className="w-full text-xs rounded-md border border-slate-200 bg-white px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500"
                                disabled={isSubmittingProfile}
                              >
                                <option value="en">English</option>
                                <option value="es">Spanish</option>
                                <option value="hi">Hindi</option>
                                <option value="ml">Malayalam</option>
                                <option value="fr">French</option>
                                <option value="ar">Arabic</option>
                              </select>
                            </div>
                          </div>

                          <div className="flex items-center gap-2 pt-2">
                            <Button
                              type="submit"
                              size="sm"
                              disabled={isSubmittingProfile}
                              className="bg-sky-700 hover:bg-sky-800 text-white text-xs"
                            >
                              {isSubmittingProfile ? "Registering..." : "Activate Patient Account"}
                            </Button>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => setShowPatientForm(false)}
                              disabled={isSubmittingProfile}
                              className="text-xs text-slate-500"
                            >
                              Cancel
                            </Button>
                          </div>
                        </form>
                      )}
                    </>
                  ) : (
                    <div className="mt-2 text-xs text-slate-500 bg-slate-50 p-3 rounded-lg border border-slate-200">
                      Self-registration is currently paused by administration. Please contact your clinical coordinator for account registration.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="pt-4 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
            <button
              onClick={() => logout().then(() => router.replace("/login"))}
              className="text-slate-500 hover:text-slate-800 flex items-center gap-1.5 transition-colors"
            >
              <LogOut size={14} />
              Sign Out
            </button>
            <span className="text-[11px] text-slate-400">
              CareRoute-X Safe Tenant System
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function AccountSetupPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-slate-50">
          <div className="flex flex-col items-center gap-3">
            <div className="h-9 w-9 animate-spin rounded-full border-3 border-sky-600 border-t-transparent" />
            <p className="text-xs text-slate-500 font-medium">Loading account details...</p>
          </div>
        </div>
      }
    >
      <AccountSetupContent />
    </Suspense>
  );
}
