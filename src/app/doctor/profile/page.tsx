"use client";

import React, { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Stethoscope,
  Building2,
  Award,
  Globe,
  Clock,
  Check,
} from "lucide-react";

export default function DoctorProfilePage() {
  const [isAvailable, setIsAvailable] = useState(true);
  const [saved, setSaved] = useState(false);

  const toggleAvailability = () => {
    setIsAvailable(!isAvailable);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          Physician Profile & Clinic Station
        </h1>
        <p className="text-sm text-slate-500">
          Clinical credentials, active practice room, and patient intake availability.
        </p>
      </div>

      <div className="p-6 rounded-2xl bg-white border border-slate-200 shadow-xs flex items-start gap-4">
        <div className="h-16 w-16 rounded-2xl bg-teal-100 text-teal-800 flex items-center justify-center font-bold text-2xl border border-teal-200 shrink-0">
          AM
        </div>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-bold text-slate-900">
              Dr. Anita Menon, MD
            </h2>
            <span className="text-xs bg-teal-100 text-teal-800 px-2 py-0.5 rounded-full font-semibold">
              Senior Consultant
            </span>
          </div>
          <p className="text-xs font-semibold text-slate-600">
            Internal Medicine & Pulmonology
          </p>
          <p className="text-xs text-slate-500 flex items-center gap-1.5 pt-1">
            <Building2 size={13} className="text-slate-400" />
            Adult Outpatient Clinic · Station Room 204
          </p>
        </div>
      </div>

      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Clinic Station Availability
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-xs">
          <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 flex items-center justify-between">
            <div>
              <span className="font-bold text-slate-900 text-sm block">
                Intake Status: {isAvailable ? "Accepting Patients" : "Station Paused"}
              </span>
              <span className="text-slate-500">
                Controls whether CareRoute-X routes new triage matches to Room 204.
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

      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Credentials & Medical Education
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-xs text-slate-700">
          <div className="flex items-start gap-2.5">
            <Award size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Medical Degree & Residency</strong>
              <span>Johns Hopkins School of Medicine · 14 Years Clinical Experience</span>
            </div>
          </div>
          <div className="flex items-start gap-2.5 border-t border-slate-100 pt-3">
            <Globe size={16} className="text-teal-600 shrink-0 mt-0.5" />
            <div>
              <strong className="block text-slate-900">Patient Consultation Languages</strong>
              <span>English, Hindi, Malayalam</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
