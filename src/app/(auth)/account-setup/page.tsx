"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
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
} from "lucide-react";

export default function AccountSetupPage() {
  const {
    user,
    isLoading,
    logout,
    refreshSession,
    completePatientProfile,
  } = useAuth();
  const router = useRouter();

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

  useEffect(() => {
    if (!isLoading) {
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
  }, [user, isLoading, router]);

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
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to check account status with server.");
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
    } catch (err: any) {
      setErrorMessage(
        err.message || "Failed to complete patient registration. Please try again."
      );
    } finally {
      setIsSubmittingProfile(false);
    }
  };

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
                            className="bg-sky-600 hover:bg-sky-700 text-white text-xs flex items-center gap-1.5"
                          >
                            <span>Complete Patient Record</span>
                            <ArrowRight size={14} />
                          </Button>
                        </div>
                      ) : (
                        <form onSubmit={handleCompletePatientProfile} className="mt-4 space-y-3 border-t border-slate-100 pt-3">
                          <div>
                            <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                              Full Legal Name *
                            </label>
                            <Input
                              type="text"
                              required
                              value={fullName}
                              onChange={(e) => setFullName(e.target.value)}
                              placeholder="e.g. Sarah Jenkins"
                              className="text-xs h-8"
                            />
                          </div>

                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                                Date of Birth *
                              </label>
                              <Input
                                type="date"
                                required
                                value={dateOfBirth}
                                onChange={(e) => setDateOfBirth(e.target.value)}
                                className="text-xs h-8"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                                Contact Phone
                              </label>
                              <Input
                                type="tel"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                                placeholder="+1 (555) 000-0000"
                                className="text-xs h-8"
                              />
                            </div>
                          </div>

                          <div>
                            <label className="block text-[11px] font-semibold text-slate-700 mb-1">
                              Emergency Contact (Name & Phone)
                            </label>
                            <Input
                              type="text"
                              value={emergencyContact}
                              onChange={(e) => setEmergencyContact(e.target.value)}
                              placeholder="e.g. David Jenkins - +1 (555) 349-8202"
                              className="text-xs h-8"
                            />
                          </div>

                          <div className="flex items-center gap-2 pt-2">
                            <Button
                              type="submit"
                              disabled={isSubmittingProfile}
                              size="sm"
                              className="bg-sky-600 hover:bg-sky-700 text-white text-xs"
                            >
                              {isSubmittingProfile ? "Registering..." : "Activate Patient Account"}
                            </Button>
                            <Button
                              type="button"
                              onClick={() => setShowPatientForm(false)}
                              variant="ghost"
                              size="sm"
                              className="text-xs text-slate-600"
                            >
                              Cancel
                            </Button>
                          </div>
                        </form>
                      )}
                    </>
                  ) : (
                    <div className="mt-2 text-xs text-slate-500 bg-slate-50 p-2.5 rounded-lg border border-slate-200">
                      Public patient self-registration is currently disabled by clinic administration. Please contact hospital reception for account setup.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Sign Out Option */}
          <div className="pt-4 border-t border-slate-100 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              Need to sign in with a different identity?
            </span>
            <Button
              onClick={logout}
              variant="ghost"
              size="sm"
              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 text-xs flex items-center gap-1.5"
            >
              <LogOut size={14} />
              <span>Sign Out</span>
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
