"use client";

import React, { useState } from "react";
import { useAuth } from "@/context/AuthContext";
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
  Edit2,
  Calendar,
} from "lucide-react";

export default function PatientProfilePage() {
  const { patientProfile } = useAuth();
  const [commPref, setCommPref] = useState(
    patientProfile.communicationPreference
  );
  const [language, setLanguage] = useState(patientProfile.preferredLanguage);
  const [isSaved, setIsSaved] = useState(false);

  const handleSavePreferences = () => {
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          My Care Profile
        </h1>
        <p className="text-sm text-slate-500">
          Personal health summary, active prescriptions, and communication
          preferences.
        </p>
      </div>

      {/* Profile Overview Banner */}
      <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col sm:flex-row items-center sm:items-start gap-4 text-center sm:text-left">
        <div className="h-16 w-16 rounded-2xl bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-2xl border border-sky-200 shrink-0">
          SJ
        </div>
        <div className="space-y-1">
          <div className="flex flex-wrap items-center justify-center sm:justify-start gap-2">
            <h2 className="text-xl font-bold text-slate-900">
              {patientProfile.fullName}
            </h2>
            <span className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
              MRN: {patientProfile.mrn}
            </span>
          </div>
          <p className="text-xs text-slate-500 flex items-center justify-center sm:justify-start gap-2">
            <span>DOB: {patientProfile.dateOfBirth}</span> ·{" "}
            <span>{patientProfile.gender}</span> ·{" "}
            <span>Blood Group: {patientProfile.bloodType}</span>
          </p>
          <p className="text-xs text-slate-600 pt-1">
            Primary Phone: {patientProfile.phone}
          </p>
        </div>
      </div>

      {/* CONFIRMED ALLERGIES */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <ShieldAlert size={16} className="text-rose-600" />
            Documented Allergies
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {patientProfile.allergies.map((allergy) => (
              <span
                key={allergy}
                className="text-xs font-semibold px-3 py-1 bg-rose-50 text-rose-800 rounded-lg border border-rose-200 flex items-center gap-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-rose-600" />
                {allergy}
              </span>
            ))}
          </div>
          <p className="text-[11px] text-slate-500 pt-1">
            Care physicians are alerted to these confirmed contraindications before prescribing.
          </p>
        </CardContent>
      </Card>

      {/* ACTIVE MEDICATIONS */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Pill size={16} className="text-sky-600" />
            Current Medications
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="space-y-2">
            {patientProfile.medications.map((med) => (
              <div
                key={med}
                className="p-3 bg-slate-50 rounded-xl border border-slate-100 flex items-center justify-between text-xs font-medium text-slate-800"
              >
                <div className="flex items-center gap-2.5">
                  <span className="h-2 w-2 rounded-full bg-sky-600" />
                  <span>{med}</span>
                </div>
                <span className="text-[11px] text-slate-400">Verified Active</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* CHRONIC CONDITIONS & VITALS CONTEXT */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Heart size={16} className="text-teal-600" />
            Chronic Conditions
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {patientProfile.chronicConditions.map((cond) => (
              <span
                key={cond}
                className="text-xs font-semibold px-3 py-1 bg-teal-50 text-teal-800 rounded-lg border border-teal-200"
              >
                {cond}
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* EMERGENCY CONTACT & PREFERENCES */}
      <Card className="border-slate-200 bg-white">
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
                Primary Emergency Contact
              </span>
              <span className="font-bold text-slate-900 text-sm">
                {patientProfile.emergencyContact.name} (
                {patientProfile.emergencyContact.relationship})
              </span>
              <span className="text-slate-600 block">
                {patientProfile.emergencyContact.phone}
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
                className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500"
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
                className="w-full h-9 rounded-lg border border-slate-300 bg-white px-3 text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500"
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
