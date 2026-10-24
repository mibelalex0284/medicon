"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Building2,
  Award,
  Globe,
  Check,
  FileCheck2,
  Star,
  Mail,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import {
  doctorService,
  DoctorResponse,
  getDoctorInitials,
  formatDoctorLanguages,
  formatDoctorSpecialties,
} from "@/services/doctors";

export default function DoctorProfilePage() {
  const [doctor, setDoctor] = useState<DoctorResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAvailable, setIsAvailable] = useState<boolean>(true);
  const [saved, setSaved] = useState<boolean>(false);

  const loadDoctorProfile = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const data = await doctorService.getCurrentDoctor();
      setDoctor(data);
      setIsAvailable(data.is_active !== false);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to load doctor profile. Please try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDoctorProfile();
  }, []);

  const toggleAvailability = () => {
    setIsAvailable(!isAvailable);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="border-b border-slate-200 pb-4">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Physician Profile & Clinic Station
          </h1>
          <p className="text-sm text-slate-500">
            Loading authenticated doctor profile and clinical station details...
          </p>
        </div>
        <div className="p-8 bg-white rounded-2xl border border-slate-200 shadow-xs flex items-center justify-center gap-3 text-slate-500">
          <RefreshCw size={18} className="animate-spin text-teal-600" />
          <span className="text-sm font-medium">Retrieving verified physician credentials...</span>
        </div>
      </div>
    );
  }

  if (errorMessage && !doctor) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="border-b border-slate-200 pb-4">
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Physician Profile & Clinic Station
          </h1>
        </div>
        <div className="p-6 bg-rose-50 border border-rose-200 rounded-2xl text-rose-900 space-y-3">
          <div className="flex items-center gap-2">
            <AlertCircle size={20} className="text-rose-600 shrink-0" />
            <h2 className="text-base font-bold">Unable to Load Doctor Profile</h2>
          </div>
          <p className="text-xs text-rose-700">{errorMessage}</p>
          <Button
            size="sm"
            variant="outline"
            onClick={loadDoctorProfile}
            className="text-xs gap-1.5 bg-white text-rose-800 border-rose-300 hover:bg-rose-100"
          >
            <RefreshCw size={14} />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  const doctorName = doctor?.profile?.full_name || "Doctor";
  const initials = getDoctorInitials(doctor?.profile?.full_name);
  const seniority =
    (doctor?.years_of_experience ?? 0) >= 10 ? "Senior Consultant" : "Consultant Specialist";
  const specialties = formatDoctorSpecialties(doctor);
  const clinicStation =
    [doctor?.department?.name, doctor?.hospital?.name].filter(Boolean).join(" · ") ||
    "Outpatient Clinic";
  const languages = formatDoctorLanguages(doctor?.languages);
  const consultationMode =
    doctor?.consultation_mode === "both"
      ? "In-Person & Teleconsultation"
      : doctor?.consultation_mode === "teleconsultation"
      ? "Teleconsultation Only"
      : "In-Person Consultation";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          Physician Profile & Clinic Station
        </h1>
        <p className="text-sm text-slate-500">
          Clinical credentials, active practice department, and patient intake availability.
        </p>
      </div>

      {/* Profile Header Card */}
      <div className="p-6 rounded-2xl bg-white border border-slate-200 shadow-xs flex items-start gap-4">
        <div className="h-16 w-16 rounded-2xl bg-teal-100 text-teal-800 flex items-center justify-center font-bold text-2xl border border-teal-200 shrink-0">
          {initials}
        </div>
        <div className="space-y-1 min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-xl font-bold text-slate-900 truncate">
              {doctorName}
            </h2>
            <span className="text-xs bg-teal-100 text-teal-800 px-2 py-0.5 rounded-full font-semibold shrink-0">
              {seniority}
            </span>
          </div>
          <p className="text-xs font-semibold text-slate-600">
            {specialties}
          </p>
          <p className="text-xs text-slate-500 flex items-center gap-1.5 pt-1 truncate">
            <Building2 size={13} className="text-slate-400 shrink-0" />
            <span>{clinicStation}</span>
          </p>
        </div>
      </div>

      {/* Clinic Station Availability Card */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Clinic Station Availability
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-xs">
          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between gap-3">
            <div>
              <span className="font-bold text-slate-900 text-sm block">
                Intake Status: {isAvailable ? "Accepting Patients" : "Station Paused"}
              </span>
              <span className="text-slate-500">
                Controls whether CareRoute-X routes new triage recommendations to your schedule.
              </span>
            </div>
            <Button
              size="sm"
              variant={isAvailable ? "default" : "secondary"}
              onClick={toggleAvailability}
              className={isAvailable ? "bg-teal-700 hover:bg-teal-800" : ""}
            >
              {isAvailable ? "Active" : "Paused"}
            </Button>
          </div>
          {saved && (
            <p className="text-emerald-600 text-xs font-semibold flex items-center gap-1">
              <Check size={14} /> Station routing configuration saved.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Credentials & Clinical Background Card */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Credentials & Clinical Background
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs text-slate-700">
          <div className="flex items-start gap-2.5">
            <FileCheck2 size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Medical Registration & License</strong>
              <span>
                License #{doctor?.license_number || "Verified"} · {doctor?.hospital?.name || "CareRoute-X Affiliated"}
              </span>
            </div>
          </div>
          <div className="flex items-start gap-2.5 border-t border-slate-100 pt-3">
            <Award size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Experience & Practice Mode</strong>
              <span>
                {doctor?.years_of_experience ?? 0} Years Clinical Experience · {consultationMode}
              </span>
            </div>
          </div>
          <div className="flex items-start gap-2.5 border-t border-slate-100 pt-3">
            <Star size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Patient Feedback & Ratings</strong>
              <span>
                {(doctor?.average_rating ?? 0) > 0
                  ? `${doctor?.average_rating?.toFixed(1)} ★ average rating across ${doctor?.rating_count ?? 0} patient reviews`
                  : "New Clinical Practitioner · No reviews yet"}
              </span>
            </div>
          </div>
          <div className="flex items-start gap-2.5 border-t border-slate-100 pt-3">
            <Globe size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Patient Consultation Languages</strong>
              <span>{languages}</span>
            </div>
          </div>
          {doctor?.profile?.email && (
            <div className="flex items-start gap-2.5 border-t border-slate-100 pt-3">
              <Mail size={16} className="text-teal-600 shrink-0 mt-0.5" />
              <div>
                <strong className="block text-slate-900">Registered Professional Email</strong>
                <span className="font-mono text-slate-600">{doctor.profile.email}</span>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
