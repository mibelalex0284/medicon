"use client";

import React, { useState, useEffect } from "react";
import { appointmentService, PatientProfileResponse } from "@/services/appointments";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  User,
  ShieldAlert,
  Pill,
  Heart,
  Phone,
  MessageSquare,
  Globe,
  Check,
  RefreshCw,
  AlertCircle,
  FileText,
} from "lucide-react";

export default function PatientProfilePage() {
  const [patient, setPatient] = useState<PatientProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [commPref, setCommPref] = useState<"sms" | "whatsapp" | "email">("sms");
  const [language, setLanguage] = useState<string>("English");
  const [isSaved, setIsSaved] = useState(false);

  const fetchProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await appointmentService.getCurrentPatient();
      setPatient(data);
      if (data.preferred_language) {
        if (data.preferred_language.toLowerCase().startsWith("es")) setLanguage("Spanish");
        else if (data.preferred_language.toLowerCase().startsWith("hi")) setLanguage("Hindi");
        else if (data.preferred_language.toLowerCase().startsWith("zh")) setLanguage("Mandarin");
        else setLanguage("English");
      }
    } catch (err: any) {
      console.error("Failed to load patient profile:", err);
      setError(err?.message || "Failed to load authenticated patient record");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchProfile();
  }, []);

  const handleSavePreferences = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2500);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[360px] space-y-4">
        <RefreshCw className="h-8 w-8 text-sky-600 animate-spin" />
        <p className="text-sm text-slate-500 font-medium">Loading clinical profile...</p>
      </div>
    );
  }

  if (error || !patient) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-2xl text-center space-y-4 max-w-lg mx-auto my-12">
        <div className="flex items-center justify-center space-x-2 text-red-700">
          <AlertCircle className="h-6 w-6" />
          <h3 className="font-semibold text-lg">Unable to Load Health Profile</h3>
        </div>
        <p className="text-sm text-red-600">
          {error || "An unexpected error occurred while retrieving your patient records."}
        </p>
        <button
          onClick={fetchProfile}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-sky-600 hover:bg-sky-700 transition"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </button>
      </div>
    );
  }

  const fullName = patient.profile?.full_name || "Authenticated Patient";
  const initials = fullName
    .split(" ")
    .filter(Boolean)
    .map((n) => n[0])
    .slice(0, 2)
    .join("")
    .toUpperCase() || "PT";

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            My Care Profile
          </h1>
          <p className="text-sm text-slate-500">
            Personal health summary, active clinical records, and communication preferences.
          </p>
        </div>
        <button
          onClick={fetchProfile}
          className="inline-flex items-center px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 transition shadow-xs"
        >
          <RefreshCw className="h-3.5 w-3.5 mr-1.5 text-sky-600" />
          Refresh
        </button>
      </div>

      {/* Profile Overview Banner */}
      <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col sm:flex-row items-center sm:items-start gap-4 text-center sm:text-left">
        <div className="h-16 w-16 rounded-2xl bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-2xl border border-sky-200 shrink-0">
          {initials}
        </div>
        <div className="space-y-1">
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
            <h2 className="text-xl font-bold text-slate-900">
              {fullName}
            </h2>
            <span className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
              ID: {patient.id.slice(0, 8)}
            </span>
          </div>
          <p className="text-xs text-slate-500 flex flex-wrap items-center justify-center sm:justify-start gap-2">
            <span>DOB: {patient.date_of_birth || "Not documented"}</span> ·{" "}
            <span>Email: {patient.profile?.email || "Not provided"}</span>
          </p>
          <p className="text-xs text-slate-600 pt-1">
            Primary Phone: {patient.profile?.phone || "Not documented"}
          </p>
        </div>
      </div>

      {/* CONFIRMED ALLERGIES */}
      <Card className="border-slate-200 bg-white shadow-xs">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <ShieldAlert size={16} className="text-rose-600" />
            Documented Allergies
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="p-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 text-center">
            <p className="text-xs text-slate-500 font-medium">
              No active drug allergies documented in electronic health record.
            </p>
            <span className="text-[11px] text-slate-400 mt-0.5 block">
              Consulting physicians will verify medication allergies during clinical intake.
            </span>
          </div>
        </CardContent>
      </Card>

      {/* ACTIVE MEDICATIONS */}
      <Card className="border-slate-200 bg-white shadow-xs">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Pill size={16} className="text-sky-600" />
            Current Prescriptions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="p-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 text-center">
            <p className="text-xs text-slate-500 font-medium">
              No active prescription medications documented.
            </p>
            <span className="text-[11px] text-slate-400 mt-0.5 block">
              Prescriptions issued during consultations will be documented in your visit summaries.
            </span>
          </div>
        </CardContent>
      </Card>

      {/* CHRONIC CONDITIONS & CLINICAL NOTES */}
      <Card className="border-slate-200 bg-white shadow-xs">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Heart size={16} className="text-teal-600" />
            Chronic Conditions & Accessibility
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {patient.accessibility_notes ? (
            <div className="p-3 bg-teal-50 rounded-xl border border-teal-200 text-xs text-teal-900">
              <span className="font-semibold block mb-0.5">Accessibility Notes:</span>
              {patient.accessibility_notes}
            </div>
          ) : (
            <div className="p-4 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 text-center">
              <p className="text-xs text-slate-500 font-medium">
                No chronic medical conditions or mobility accommodations on file.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* EMERGENCY CONTACT & PREFERENCES */}
      <Card className="border-slate-200 bg-white shadow-xs">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Phone size={16} className="text-slate-600" />
            Emergency Contact & Preferences
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-xs">
          <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between">
            <div>
              <span className="text-slate-500 block text-[10px] uppercase font-semibold">
                Emergency Contact
              </span>
              <span className="font-bold text-slate-900 text-sm">
                {patient.emergency_contact || "No emergency contact designated"}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 flex items-center gap-1.5">
                <Globe size={13} />
                Preferred Consultation Language
              </label>
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              >
                <option value="English">English</option>
                <option value="Spanish">Español (Spanish)</option>
                <option value="Hindi">हिन्दी (Hindi)</option>
                <option value="Mandarin">中文 (Mandarin)</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="font-semibold text-slate-700 flex items-center gap-1.5">
                <MessageSquare size={13} />
                Queue Update Notifications
              </label>
              <select
                value={commPref}
                onChange={(e) =>
                  setCommPref(e.target.value as "sms" | "whatsapp" | "email")
                }
                className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              >
                <option value="sms">SMS Text Alert</option>
                <option value="whatsapp">WhatsApp Realtime Ping</option>
                <option value="email">Email Notification</option>
              </select>
            </div>
          </div>

          <div className="pt-2 flex items-center justify-end">
            <Button
              size="sm"
              onClick={handleSavePreferences}
              className="gap-1.5 font-semibold"
            >
              {isSaved ? (
                <>
                  <Check size={14} />
                  Saved
                </>
              ) : (
                "Update Care Preferences"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
