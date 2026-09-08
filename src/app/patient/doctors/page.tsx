"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { doctorService } from "@/services/doctors";
import { appointmentService } from "@/services/appointments";
import { useAuth } from "@/context/AuthContext";
import { Doctor } from "@/types";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Stethoscope,
  Sparkles,
  CheckCircle,
  Clock,
  Languages,
  Award,
  CalendarCheck,
  ChevronDown,
  Building2,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";

export default function DoctorMatchingPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [recommendedDoctor, setRecommendedDoctor] = useState<Doctor | null>(null);
  const [alternativeDoctors, setAlternativeDoctors] = useState<Doctor[]>([]);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState("Today, 11:30 AM");
  const [isBooking, setIsBooking] = useState(false);

  useEffect(() => {
    let specialties = ["Internal Medicine"];
    if (typeof window !== "undefined") {
      const stored = sessionStorage.getItem("careroute_triage_specialties");
      if (stored) {
        try {
          specialties = JSON.parse(stored);
        } catch {
          // fallback
        }
      }
    }

    const { recommendedDoctor, alternativeDoctors } =
      doctorService.getExplainableMatches(specialties, "English");

    setRecommendedDoctor(recommendedDoctor);
    setAlternativeDoctors(alternativeDoctors);
  }, []);

  const handleBookAppointment = (doctor: Doctor) => {
    if (!user) return;
    setIsBooking(true);

    const storedConcern =
      typeof window !== "undefined"
        ? sessionStorage.getItem("careroute_patient_concern") ||
          "Persistent dry cough & chest discomfort"
        : "Persistent dry cough & chest discomfort";

    setTimeout(() => {
      appointmentService.createAppointment({
        patientId: user.id,
        doctorId: doctor.id,
        doctorName: doctor.name,
        doctorSpecialty: doctor.specialty,
        department: doctor.department,
        date: "Today",
        timeSlot: "11:30 AM",
        status: "scheduled",
        reasonForVisit: storedConcern,
        triageUrgency: "routine",
      });

      setIsBooking(false);
      router.push("/patient/appointments");
    }, 400);
  };

  if (!recommendedDoctor) {
    return (
      <div className="p-12 text-center text-sm text-slate-500">
        Matching with available physicians...
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Intro Communication */}
      <div className="space-y-1.5">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-sky-100 text-sky-800 text-xs font-semibold">
          <Sparkles size={14} />
          Care Direction & Match
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          We found doctors who can help with your concern
        </h1>
        <p className="text-sm text-slate-600">
          Ranked using clinical intake suitability, current outpatient wait
          times, and language preferences.
        </p>
      </div>

      {/* PRIMARY RECOMMENDED DOCTOR (Prominently spotlighted, not an identical card wall) */}
      <section aria-label="Primary Recommended Doctor">
        <Card className="border-2 border-sky-500 shadow-md overflow-hidden bg-white">
          <div className="bg-sky-600 px-5 py-2.5 text-white flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
              <Award size={15} />
              Best Clinical Match
            </span>
            <span className="text-xs bg-sky-700/80 px-2 py-0.5 rounded font-mono">
              Match Score: {recommendedDoctor.matchScore}%
            </span>
          </div>

          <CardContent className="p-5 md:p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
              <div className="flex items-start gap-3.5">
                <div className="h-14 w-14 rounded-2xl bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-xl shrink-0 border border-sky-200">
                  {recommendedDoctor.name
                    .replace("Dr. ", "")
                    .split(" ")
                    .map((n) => n[0])
                    .join("")}
                </div>
                <div className="space-y-1">
                  <h2 className="text-xl font-bold text-slate-900">
                    {recommendedDoctor.name}
                  </h2>
                  <p className="text-xs font-semibold text-sky-700">
                    {recommendedDoctor.title} · {recommendedDoctor.specialty}
                  </p>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 size={13} className="text-slate-400" />
                    {recommendedDoctor.department} ({recommendedDoctor.roomNumber})
                  </p>
                </div>
              </div>

              {/* Live Wait Range Indicator */}
              <div className="text-left sm:text-right space-y-1">
                <span className="text-[11px] text-slate-500 uppercase font-semibold block">
                  Current Wait Range
                </span>
                <WaitEstimate
                  min={recommendedDoctor.currentWaitRange.min}
                  max={recommendedDoctor.currentWaitRange.max}
                  size="md"
                />
              </div>
            </div>

            {/* EXPLAINABLE RANKING: "Why this doctor?" */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <ShieldCheck size={14} className="text-sky-600" />
                Why this doctor?
              </h3>
              <ul className="space-y-1.5 text-xs text-slate-700">
                {recommendedDoctor.matchReasons?.map((reason, idx) => (
                  <li key={idx} className="flex items-center gap-2">
                    <CheckCircle
                      size={14}
                      className="text-emerald-600 shrink-0"
                    />
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Key Clinical Details */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs text-slate-600 pt-1">
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Experience
                </span>
                <span className="font-semibold text-slate-800">
                  {recommendedDoctor.experienceYears} Years Practice
                </span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Languages
                </span>
                <span className="font-semibold text-slate-800">
                  {recommendedDoctor.languages.join(", ")}
                </span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100 col-span-2 sm:col-span-1">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Queue Status
                </span>
                <span className="font-semibold text-emerald-700">
                  {recommendedDoctor.activeQueueCount} Patients Ahead
                </span>
              </div>
            </div>

            {/* Booking Action */}
            <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                Available slot:{" "}
                <span className="font-semibold text-slate-800">
                  Today at 11:30 AM
                </span>
              </div>
              <Button
                size="lg"
                onClick={() => handleBookAppointment(recommendedDoctor)}
                isLoading={isBooking}
                className="w-full sm:w-auto font-semibold gap-2 shadow-sm"
              >
                Book with {recommendedDoctor.name.split(" ")[1]}
                <ArrowRight size={16} />
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ALTERNATIVE DOCTORS (Collapsible / Non-intrusive) */}
      <div className="space-y-3 pt-2">
        <button
          type="button"
          onClick={() => setShowAlternatives(!showAlternatives)}
          className="flex items-center justify-between w-full p-3 rounded-xl bg-slate-100/80 hover:bg-slate-200/70 text-xs font-semibold text-slate-700 transition-colors"
        >
          <span>
            Explore alternative physicians in other departments (
            {alternativeDoctors.length})
          </span>
          <ChevronDown
            size={16}
            className={`transition-transform duration-200 ${
              showAlternatives ? "rotate-180" : ""
            }`}
          />
        </button>

        {showAlternatives && (
          <div className="space-y-3">
            {alternativeDoctors.map((doc) => (
              <Card key={doc.id} className="border-slate-200">
                <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="space-y-0.5">
                    <h4 className="text-sm font-bold text-slate-900">
                      {doc.name}
                    </h4>
                    <p className="text-xs text-slate-500">
                      {doc.specialty} · {doc.department}
                    </p>
                    <div className="pt-1 flex items-center gap-2">
                      <WaitEstimate
                        min={doc.currentWaitRange.min}
                        max={doc.currentWaitRange.max}
                        size="sm"
                      />
                      <span className="text-[11px] text-slate-400">
                        {doc.languages.join(", ")}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleBookAppointment(doc)}
                  >
                    Select Doctor
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
