"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  doctorService,
  DoctorRecommendationResponse,
  DoctorRecommendationItem,
} from "@/services/doctors";
import { appointmentService } from "@/services/appointments";
import { useAuth } from "@/context/AuthContext";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EMERGENCY_CONTACT } from "@/lib/constants";
import {
  Sparkles,
  CheckCircle,
  Clock,
  Award,
  ChevronDown,
  Building2,
  ArrowRight,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  AlertCircle,
  RotateCcw,
  Activity,
  PhoneCall,
  User,
  Star,
} from "lucide-react";

function formatFactorLabel(factor: string): string {
  switch (factor.toLowerCase()) {
    case "specialty":
      return "Direct clinical specialty match";
    case "availability":
      return "Immediate appointment availability";
    case "wait":
      return "Low estimated wait time";
    case "experience":
      return "Extensive clinical experience";
    case "rating":
      return "High patient satisfaction & rating reliability";
    case "language":
      return "Preferred language match";
    case "preference":
      return "Aligned with patient preference";
    default:
      return factor;
  }
}

function DoctorMatchingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [response, setResponse] = useState<DoctorRecommendationResponse | null>(null);
  const [showAlternatives, setShowAlternatives] = useState(false);
  const [isBooking, setIsBooking] = useState(false);

  // Retrieve session_id from query params or sessionStorage fallback
  const urlSessionId = searchParams.get("session_id") || searchParams.get("sessionId");

  useEffect(() => {
    let isMounted = true;

    async function fetchRecommendations() {
      setIsLoading(true);
      setErrorMessage(null);

      const resolvedSessionId =
        urlSessionId ||
        (typeof window !== "undefined"
          ? sessionStorage.getItem("careroute_triage_session_id")
          : null);

      const storedSpecialtyId =
        typeof window !== "undefined"
          ? sessionStorage.getItem("careroute_triage_specialty_id")
          : null;

      if (!resolvedSessionId && !storedSpecialtyId) {
        if (isMounted) {
          setIsLoading(false);
          setErrorMessage("NO_SESSION");
        }
        return;
      }

      try {
        const payload: { triage_session_id?: string; specialty_id?: string } = {};
        if (resolvedSessionId) {
          payload.triage_session_id = resolvedSessionId;
        } else if (storedSpecialtyId) {
          payload.specialty_id = storedSpecialtyId;
        }

        const data = await doctorService.recommendDoctors(payload);
        if (isMounted) {
          setResponse(data);
        }
      } catch (err: unknown) {
        if (isMounted) {
          const msg =
            err instanceof Error
              ? err.message
              : "Failed to retrieve doctor recommendations from clinical service.";
          setErrorMessage(msg);
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    fetchRecommendations();

    return () => {
      isMounted = false;
    };
  }, [urlSessionId]);

  const handleBookAppointment = (item: DoctorRecommendationItem) => {
    if (!user) return;
    setIsBooking(true);

    const storedConcern =
      typeof window !== "undefined"
        ? sessionStorage.getItem("careroute_patient_concern") ||
          "Outpatient clinical consultation"
        : "Outpatient clinical consultation";

    const specialtyName =
      item.doctor.specialties?.[0]?.specialty?.name ||
      response?.applied_specialty_name ||
      "Specialist";

    setTimeout(() => {
      appointmentService.createAppointment({
        patientId: user.id,
        doctorId: item.doctor.id,
        doctorName: item.doctor.profile.full_name,
        doctorSpecialty: specialtyName,
        department: item.doctor.department?.name || "Outpatient Clinic",
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

  // 1. Loading State
  if (isLoading) {
    return (
      <div className="max-w-2xl mx-auto p-12 text-center space-y-4">
        <div className="inline-flex items-center justify-center p-3 rounded-full bg-sky-50 text-sky-600 animate-spin">
          <Activity size={24} />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-bold text-slate-900">
            Matching with Clinical Specialists...
          </h2>
          <p className="text-sm text-slate-500">
            Evaluating doctor availability, clinical specialty match, and estimated outpatient wait times.
          </p>
        </div>
      </div>
    );
  }

  // 2. Missing Session State
  if (errorMessage === "NO_SESSION") {
    return (
      <div className="max-w-2xl mx-auto p-8 rounded-2xl bg-white border border-slate-200 shadow-sm text-center space-y-4">
        <div className="inline-flex p-3 rounded-full bg-amber-50 text-amber-600">
          <AlertTriangle size={24} />
        </div>
        <div className="space-y-1.5">
          <h2 className="text-lg font-bold text-slate-900">
            No Active Triage Intake Found
          </h2>
          <p className="text-sm text-slate-600 max-w-md mx-auto">
            Doctor recommendations are driven by clinical triage navigation. Please complete a brief symptom intake so we can match you with the appropriate specialty.
          </p>
        </div>
        <div className="pt-2">
          <Link href="/patient/find-care">
            <Button size="md" className="font-semibold gap-2">
              Start Guided Triage
              <ArrowRight size={16} />
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  // 3. Error State
  if (errorMessage) {
    return (
      <div className="max-w-2xl mx-auto p-6 rounded-2xl bg-white border border-rose-200 shadow-sm space-y-4">
        <div className="flex items-start gap-3">
          <AlertCircle size={22} className="text-rose-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h3 className="text-base font-bold text-rose-900">
              Doctor Recommendation Service Unavailable
            </h3>
            <p className="text-sm text-rose-700">{errorMessage}</p>
          </div>
        </div>
        <div className="pt-2 flex items-center gap-3">
          <Button
            size="sm"
            onClick={() => window.location.reload()}
            variant="outline"
            className="gap-2 text-xs"
          >
            <RotateCcw size={14} />
            Retry
          </Button>
          <Link href="/patient/find-care">
            <Button size="sm" variant="ghost" className="text-xs text-slate-600">
              Return to Triage Intake
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  // 4. Emergency Escalation State (Requirement D)
  const isEmergency =
    response?.is_emergency_escalation ||
    response?.status === "EMERGENCY_ESCALATION";

  if (isEmergency) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div
          role="alert"
          className="rounded-2xl border-2 border-red-600 bg-red-50 p-5 md:p-6 text-red-950 shadow-md space-y-4"
        >
          <div className="flex items-start gap-3.5">
            <div className="p-2.5 bg-red-600 text-white rounded-xl shrink-0">
              <ShieldAlert size={26} className="stroke-[2.5]" />
            </div>
            <div className="space-y-2 flex-1">
              <div className="flex items-center justify-between">
                <h2 className="text-lg md:text-xl font-bold text-red-950 tracking-tight">
                  Emergency Medical Notice
                </h2>
                <span className="text-[11px] font-bold uppercase tracking-wider bg-red-200 text-red-950 px-2.5 py-0.5 rounded border border-red-300">
                  Immediate Evaluation
                </span>
              </div>
              <p className="text-sm text-red-900 leading-relaxed font-medium">
                {response?.escalation_notice ||
                  "Triage assessment indicated high clinical urgency or red-flag emergency symptoms. Immediate emergency medical evaluation is advised. Routine outpatient doctor selection is not a substitute for emergency care."}
              </p>
              <div className="pt-2 flex flex-wrap items-center gap-3">
                <a
                  href={`tel:${EMERGENCY_CONTACT.primaryNumber}`}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-red-700 hover:bg-red-800 text-white text-sm font-bold rounded-xl shadow-sm transition-colors"
                >
                  <PhoneCall size={16} />
                  {EMERGENCY_CONTACT.displayLabel}
                </a>
                <Link href="/patient/find-care">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-red-300 bg-white hover:bg-red-100 text-red-900"
                  >
                    Return to Patient Dashboard
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // 5. Empty State: No Eligible Doctors (Requirement E)
  const recommendations = response?.recommendations || [];
  if (response?.status === "NO_ELIGIBLE_DOCTORS" || recommendations.length === 0) {
    return (
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="p-8 rounded-2xl bg-white border border-slate-200 text-center space-y-4 shadow-sm">
          <div className="inline-flex p-3 rounded-full bg-slate-100 text-slate-500">
            <Building2 size={24} />
          </div>
          <div className="space-y-1.5">
            <h2 className="text-lg font-bold text-slate-900">
              No Eligible Doctors Available
            </h2>
            <p className="text-sm text-slate-600 max-w-md mx-auto">
              {response?.message ||
                `No active physicians currently match the required clinical specialty (${response?.applied_specialty_name || "Requested Specialty"}) in this hospital facility.`}
            </p>
          </div>
          <div className="pt-2 flex justify-center gap-3">
            <Link href="/patient/find-care">
              <Button size="md" variant="outline" className="text-xs">
                Start New Triage
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // 6. Normal Doctor Recommendation State (Requirement C)
  const primaryDoc = recommendations[0];
  const alternativeDocs = recommendations.slice(1);

  const primarySpecialtyName =
    primaryDoc.doctor.specialties?.[0]?.specialty?.name ||
    response?.applied_specialty_name ||
    "Specialist";

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Intro Communication */}
      <div className="space-y-1.5">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-sky-100 text-sky-800 text-xs font-semibold">
          <Sparkles size={14} />
          Care Direction & Clinical Match
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          Recommended Specialists
        </h1>
        <p className="text-sm text-slate-600">
          Ranked by backend clinical matching for{" "}
          <span className="font-semibold text-slate-800">
            {response?.applied_specialty_name || primarySpecialtyName}
          </span>
          , considering schedule availability, queue load, and experience.
        </p>
      </div>

      {/* PRIMARY RECOMMENDED DOCTOR */}
      <section aria-label="Primary Recommended Doctor">
        <Card className="border-2 border-sky-500 shadow-md overflow-hidden bg-white">
          <div className="bg-sky-600 px-5 py-2.5 text-white flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider flex items-center gap-1.5">
              <Award size={15} />
              Best Clinical Match · Rank #{primaryDoc.rank}
            </span>
            {primaryDoc.score !== undefined && (
              <span className="text-xs bg-sky-700/80 px-2 py-0.5 rounded font-mono font-semibold">
                Match Score: {Math.round(primaryDoc.score * 100)}%
              </span>
            )}
          </div>

          <CardContent className="p-5 md:p-6 space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
              <div className="flex items-start gap-3.5">
                <div className="h-14 w-14 rounded-2xl bg-sky-100 text-sky-800 flex items-center justify-center font-bold text-xl shrink-0 border border-sky-200">
                  {primaryDoc.doctor.profile.full_name
                    .replace("Dr. ", "")
                    .split(" ")
                    .map((n) => n[0])
                    .join("")}
                </div>
                <div className="space-y-1">
                  <h2 className="text-xl font-bold text-slate-900">
                    {primaryDoc.doctor.profile.full_name}
                  </h2>
                  <p className="text-xs font-semibold text-sky-700">
                    {primarySpecialtyName}
                  </p>
                  <p className="text-xs text-slate-500 flex items-center gap-1">
                    <Building2 size={13} className="text-slate-400" />
                    {primaryDoc.doctor.hospital?.name || "Metro Central Hospital"}
                    {primaryDoc.doctor.department?.name && ` · ${primaryDoc.doctor.department.name}`}
                  </p>
                </div>
              </div>

              {/* Wait Time Indicator */}
              <div className="text-left sm:text-right space-y-1">
                <span className="text-[11px] text-slate-500 uppercase font-semibold block">
                  Estimated Wait
                </span>
                <WaitEstimate
                  min={primaryDoc.estimated_wait_minutes}
                  max={primaryDoc.estimated_wait_minutes}
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
              <p className="text-xs font-medium text-slate-800 leading-relaxed">
                {primaryDoc.explanation}
              </p>

              {primaryDoc.matched_factors && primaryDoc.matched_factors.length > 0 && (
                <ul className="space-y-1.5 text-xs text-slate-700 pt-1">
                  {primaryDoc.matched_factors.map((factor, idx) => (
                    <li key={idx} className="flex items-center gap-2">
                      <CheckCircle size={14} className="text-emerald-600 shrink-0" />
                      <span>{formatFactorLabel(factor)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Key Clinical Details */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs text-slate-600 pt-1">
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Experience
                </span>
                <span className="font-semibold text-slate-800">
                  {primaryDoc.doctor.years_of_experience} Years
                </span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Rating
                </span>
                <span className="font-semibold text-slate-800 flex items-center gap-1">
                  <Star size={12} className="text-amber-500 fill-amber-500" />
                  {primaryDoc.doctor.average_rating > 0
                    ? `${primaryDoc.doctor.average_rating.toFixed(1)} (${primaryDoc.doctor.rating_count})`
                    : "New"}
                </span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Mode
                </span>
                <span className="font-semibold text-slate-800 capitalize">
                  {primaryDoc.consultation_mode.replace("_", " ")}
                </span>
              </div>
              <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Languages
                </span>
                <span className="font-semibold text-slate-800 uppercase">
                  {primaryDoc.doctor.languages || "EN"}
                </span>
              </div>
            </div>

            {/* Booking Action */}
            <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="text-xs text-slate-500">
                Next available slot:{" "}
                <span className="font-semibold text-slate-800">
                  Today at 11:30 AM
                </span>
              </div>
              <Button
                size="lg"
                onClick={() => handleBookAppointment(primaryDoc)}
                isLoading={isBooking}
                className="w-full sm:w-auto font-semibold gap-2 shadow-sm"
              >
                Book with {primaryDoc.doctor.profile.full_name.split(" ")[1] || "Doctor"}
                <ArrowRight size={16} />
              </Button>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ALTERNATIVE DOCTORS */}
      {alternativeDocs.length > 0 && (
        <div className="space-y-3 pt-2">
          <button
            type="button"
            onClick={() => setShowAlternatives(!showAlternatives)}
            className="flex items-center justify-between w-full p-3 rounded-xl bg-slate-100/80 hover:bg-slate-200/70 text-xs font-semibold text-slate-700 transition-colors"
          >
            <span>
              Explore alternative physicians ({alternativeDocs.length})
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
              {alternativeDocs.map((item) => {
                const docSpec =
                  item.doctor.specialties?.[0]?.specialty?.name ||
                  response?.applied_specialty_name ||
                  "Specialist";

                return (
                  <Card key={item.doctor_id} className="border-slate-200">
                    <CardContent className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-bold text-slate-900">
                            {item.doctor.profile.full_name}
                          </h4>
                          <span className="text-[10px] font-mono bg-slate-100 px-1.5 py-0.5 rounded text-slate-600 font-semibold">
                            Rank #{item.rank}
                          </span>
                          {item.score !== undefined && (
                            <span className="text-[10px] font-mono bg-sky-50 text-sky-700 px-1.5 py-0.5 rounded font-semibold">
                              {Math.round(item.score * 100)}%
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-500">
                          {docSpec} · {item.doctor.hospital?.name || "Hospital"}
                        </p>
                        <p className="text-xs text-slate-600 italic">
                          {item.explanation}
                        </p>
                        <div className="pt-1 flex items-center gap-3">
                          <WaitEstimate
                            min={item.estimated_wait_minutes}
                            max={item.estimated_wait_minutes}
                            size="sm"
                          />
                          <span className="text-[11px] text-slate-400">
                            {item.doctor.years_of_experience} yrs exp
                          </span>
                          {item.doctor.average_rating > 0 && (
                            <span className="text-[11px] text-slate-500 flex items-center gap-0.5">
                              <Star size={11} className="text-amber-500 fill-amber-500" />
                              {item.doctor.average_rating.toFixed(1)}
                            </span>
                          )}
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleBookAppointment(item)}
                        className="shrink-0"
                      >
                        Select Doctor
                      </Button>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function DoctorMatchingPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-2xl mx-auto p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-slate-100 text-slate-400 animate-spin">
            <Activity size={20} />
          </div>
          <p className="text-sm text-slate-500">Loading doctor recommendations...</p>
        </div>
      }
    >
      <DoctorMatchingContent />
    </Suspense>
  );
}
