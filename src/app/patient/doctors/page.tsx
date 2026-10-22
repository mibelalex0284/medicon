"use client";

import React, { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import {
  doctorService,
  DoctorRecommendationResponse,
  DoctorRecommendationItem,
  AvailableSlot,
} from "@/services/doctors";
import {
  appointmentService,
  AppointmentApiError,
  formatTimeSlot,
  formatAppointmentDate,
} from "@/services/appointments";
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
  Calendar,
  X,
  Check,
} from "lucide-react";

function formatFactorLabel(factor: string): string {
  switch (factor.toLowerCase()) {
    case "specialty":
    case "specialty_primary":
    case "specialty_secondary":
      return "Direct clinical specialty match";
    case "availability":
    case "available_slots":
      return "Immediate appointment availability";
    case "wait":
    case "shorter_wait":
    case "moderate_wait":
      return "Low estimated wait time";
    case "experience":
    case "established_experience":
      return "Extensive clinical experience";
    case "rating":
    case "reliable_rating":
      return "Patient rating & feedback";
    case "language":
    case "language_match":
      return "Explicit preferred language match";
    case "preference":
    case "patient_preference":
      return "Aligned with patient preference";
    default:
      return factor;
  }
}

function getDoctorDisplaySpecialty(
  doctor: DoctorRecommendationItem["doctor"],
  appliedSpecialtyName?: string | null
): string {
  if (appliedSpecialtyName) {
    const matched = doctor.specialties?.find(
      (s) => s.specialty?.name?.toLowerCase() === appliedSpecialtyName.toLowerCase()
    );
    if (matched?.specialty?.name) return matched.specialty.name;
  }
  const primary = doctor.specialties?.find((s) => s.is_primary);
  if (primary?.specialty?.name) return primary.specialty.name;
  return (
    doctor.specialties?.[0]?.specialty?.name ||
    appliedSpecialtyName ||
    "Specialist"
  );
}

function DoctorMatchingContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [response, setResponse] = useState<DoctorRecommendationResponse | null>(null);
  const [showAlternatives, setShowAlternatives] = useState(false);

  // Real Slot Availability & Booking State
  const [selectedDoctorForBooking, setSelectedDoctorForBooking] = useState<DoctorRecommendationItem | null>(null);
  const [bookingDate, setBookingDate] = useState<string>(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [availableSlots, setAvailableSlots] = useState<AvailableSlot[]>([]);
  const [isLoadingSlots, setIsLoadingSlots] = useState(false);
  const [slotsError, setSlotsError] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<AvailableSlot | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [isBooking, setIsBooking] = useState(false);
  const [bookingSuccess, setBookingSuccess] = useState(false);

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

  // Load real doctor availability whenever a doctor is selected or date changes
  useEffect(() => {
    if (!selectedDoctorForBooking) return;
    let isMounted = true;
    setIsLoadingSlots(true);
    setSlotsError(null);
    setSelectedSlot(null);
    setBookingError(null);

    doctorService
      .getDoctorAvailability(selectedDoctorForBooking.doctor.id, bookingDate)
      .then((avail) => {
        if (isMounted) {
          let slots = avail.slots || [];
          // Defensive client-side past slot exclusion if booking date is today
          const todayStr = new Date().toISOString().split("T")[0];
          if (bookingDate === todayStr) {
            const now = new Date();
            const currentHour = now.getHours();
            const currentMin = now.getMinutes();
            slots = slots.filter((slot) => {
              const [h, m] = slot.start_time.split(":").map(Number);
              return h > currentHour || (h === currentHour && m > currentMin);
            });
          }
          setAvailableSlots(slots);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          setSlotsError(
            err instanceof Error
              ? err.message
              : "Could not retrieve doctor schedule availability."
          );
          setAvailableSlots([]);
        }
      })
      .finally(() => {
        if (isMounted) {
          setIsLoadingSlots(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [selectedDoctorForBooking, bookingDate]);

  const handleOpenSlotSelection = (item: DoctorRecommendationItem) => {
    setSelectedDoctorForBooking(item);
    setSelectedSlot(null);
    setBookingError(null);
    setBookingSuccess(false);
  };

  const handleCloseSlotSelection = () => {
    setSelectedDoctorForBooking(null);
    setSelectedSlot(null);
    setBookingError(null);
    setBookingSuccess(false);
  };

  const handleConfirmBooking = async () => {
    if (!selectedDoctorForBooking || !selectedSlot || isBooking) return;
    setIsBooking(true);
    setBookingError(null);

    try {
      // 1. Authoritative patient identity from backend /patients/me
      let patientId = user?.id || "";
      try {
        const patientRecord = await appointmentService.getCurrentPatient();
        if (patientRecord?.id) {
          patientId = patientRecord.id;
        }
      } catch {
        // Fallback to user.id if /patients/me is unavailable
      }

      const storedConcern =
        typeof window !== "undefined"
          ? sessionStorage.getItem("careroute_patient_concern") ||
            "Outpatient clinical consultation"
          : "Outpatient clinical consultation";

      const hospitalId =
        selectedDoctorForBooking.doctor.hospital_id ||
        selectedDoctorForBooking.doctor.hospital?.id ||
        response?.applied_hospital_id ||
        "";

      await appointmentService.bookAppointment({
        patient_id: patientId,
        doctor_id: selectedDoctorForBooking.doctor.id,
        hospital_id: hospitalId,
        appointment_date: bookingDate,
        scheduled_start: selectedSlot.start_time,
        scheduled_end: selectedSlot.end_time,
        appointment_type: "in_person",
        reason: storedConcern,
      });

      setBookingSuccess(true);
      setTimeout(() => {
        router.push("/patient/appointments?booked=true");
      }, 700);
    } catch (err: unknown) {
      if (err instanceof AppointmentApiError) {
        if (err.status === 409) {
          setBookingError(
            "This slot was just booked by another patient or conflicts with existing appointments. Please select another slot."
          );
          // Refresh slots to show updated availability
          if (selectedDoctorForBooking) {
            doctorService
              .getDoctorAvailability(selectedDoctorForBooking.doctor.id, bookingDate)
              .then((avail) => setAvailableSlots(avail.slots || []))
              .catch(() => {});
          }
        } else {
          setBookingError(err.message);
        }
      } else if (err instanceof Error) {
        setBookingError(err.message);
      } else {
        setBookingError("Failed to book appointment. Please check your connection and try again.");
      }
    } finally {
      setIsBooking(false);
    }
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
        {(response?.urgency === "HIGH" || response?.escalation_notice) && (
          <div
            role="status"
            className="rounded-2xl border-2 border-amber-500 bg-amber-50 p-4 md:p-5 text-amber-950 shadow-sm space-y-2"
          >
            <div className="flex items-start gap-3">
              <div className="p-2 bg-amber-500 text-white rounded-xl shrink-0 mt-0.5">
                <AlertTriangle size={20} className="stroke-[2.5]" />
              </div>
              <div className="space-y-1.5 flex-1">
                <div className="flex items-center justify-between">
                  <h3 className="text-base font-bold text-amber-950 tracking-tight">
                    High Clinical Urgency Notice
                  </h3>
                  <span className="text-[11px] font-bold uppercase tracking-wider bg-amber-200 text-amber-900 px-2 py-0.5 rounded border border-amber-300">
                    Prompt Evaluation Advised
                  </span>
                </div>
                <p className="text-xs md:text-sm text-amber-900 leading-relaxed font-medium">
                  {response?.escalation_notice ||
                    "Your triage assessment indicates elevated clinical urgency. Absence of red-flag symptoms does not guarantee safety. If your condition worsens suddenly, seek immediate emergency medical care."}
                </p>
                <div className="pt-1">
                  <a
                    href={`tel:${EMERGENCY_CONTACT.primaryNumber}`}
                    className="inline-flex items-center gap-1.5 text-xs font-bold text-amber-950 underline hover:text-amber-800"
                  >
                    <PhoneCall size={13} />
                    Emergency Hotline ({EMERGENCY_CONTACT.primaryNumber})
                  </a>
                </div>
              </div>
            </div>
          </div>
        )}
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

  const primarySpecialtyName = getDoctorDisplaySpecialty(
    primaryDoc.doctor,
    response?.applied_specialty_name
  );

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

      {/* High Urgency Clinical Notice (Non-Emergency) */}
      {(response?.urgency === "HIGH" || response?.escalation_notice) && (
        <div
          role="status"
          className="rounded-2xl border-2 border-amber-500 bg-amber-50 p-4 md:p-5 text-amber-950 shadow-sm space-y-2"
        >
          <div className="flex items-start gap-3">
            <div className="p-2 bg-amber-500 text-white rounded-xl shrink-0 mt-0.5">
              <AlertTriangle size={20} className="stroke-[2.5]" />
            </div>
            <div className="space-y-1.5 flex-1">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-bold text-amber-950 tracking-tight">
                  High Clinical Urgency Notice
                </h3>
                <span className="text-[11px] font-bold uppercase tracking-wider bg-amber-200 text-amber-900 px-2 py-0.5 rounded border border-amber-300">
                  Priority Scheduling Advised
                </span>
              </div>
              <p className="text-xs md:text-sm text-amber-900 leading-relaxed font-medium">
                {response?.escalation_notice ||
                  "Your triage assessment indicates elevated clinical urgency. Please schedule a prompt consultation below. Note: Absence of red-flag symptoms does not guarantee safety. If your condition worsens suddenly, seek immediate emergency medical care."}
              </p>
              <div className="pt-1 flex items-center gap-2">
                <span className="text-xs text-amber-800">
                  Experiencing sudden severe symptoms or worsening distress?
                </span>
                <a
                  href={`tel:${EMERGENCY_CONTACT.primaryNumber}`}
                  className="inline-flex items-center gap-1 text-xs font-bold text-amber-950 underline hover:text-amber-800"
                >
                  <PhoneCall size={12} />
                  Call {EMERGENCY_CONTACT.primaryNumber}
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

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
                Next available consultation:{" "}
                <span className="font-semibold text-slate-800">
                  Select date & slot
                </span>
              </div>
              <Button
                size="lg"
                onClick={() => handleOpenSlotSelection(primaryDoc)}
                className="w-full sm:w-auto font-semibold gap-2 shadow-sm"
              >
                Choose Slot & Book
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
                const docSpec = getDoctorDisplaySpecialty(
                  item.doctor,
                  response?.applied_specialty_name
                );

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
                        onClick={() => handleOpenSlotSelection(item)}
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
      {/* SLOT SELECTION AND BOOKING MODAL */}
      {selectedDoctorForBooking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
            {/* Modal Header */}
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-gradient-to-r from-slate-50 to-white">
              <div>
                <h3 className="text-base font-bold text-slate-900">
                  Select Appointment Slot
                </h3>
                <p className="text-xs text-slate-500">
                  {selectedDoctorForBooking.doctor.profile.full_name} ·{" "}
                  {getDoctorDisplaySpecialty(
                    selectedDoctorForBooking.doctor,
                    response?.applied_specialty_name
                  )}
                </p>
              </div>
              <button
                type="button"
                onClick={handleCloseSlotSelection}
                disabled={isBooking}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-5">
              {/* Date Selector */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-1.5">
                  Appointment Date
                </label>
                <div className="relative">
                  <input
                    type="date"
                    value={bookingDate}
                    min={new Date().toISOString().split("T")[0]}
                    onChange={(e) => {
                      setBookingDate(e.target.value);
                      setSelectedSlot(null);
                      setBookingError(null);
                    }}
                    disabled={isBooking}
                    className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 bg-slate-50 text-slate-900 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all"
                  />
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  Showing available consultation windows for {formatAppointmentDate(bookingDate)}
                </p>
              </div>

              {/* Slot Grid / States */}
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wide mb-2">
                  Available Slots
                </label>

                {isLoadingSlots ? (
                  <div className="p-8 text-center space-y-2 bg-slate-50 rounded-xl border border-slate-100">
                    <Activity size={20} className="animate-spin text-sky-600 mx-auto" />
                    <p className="text-xs text-slate-500 font-medium">
                      Checking doctor schedule...
                    </p>
                  </div>
                ) : slotsError ? (
                  <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-start gap-2.5">
                    <AlertCircle size={16} className="text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold">Unable to load schedule</p>
                      <p className="mt-0.5 text-amber-700">{slotsError}</p>
                    </div>
                  </div>
                ) : availableSlots.length === 0 ? (
                  <div className="p-6 text-center space-y-1.5 bg-slate-50 rounded-xl border border-slate-100">
                    <Calendar size={22} className="text-slate-400 mx-auto" />
                    <p className="text-xs font-semibold text-slate-700">
                      No open slots for this date
                    </p>
                    <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
                      All consultation windows on {bookingDate} are booked or unavailable. Please choose another date.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-56 overflow-y-auto pr-1">
                    {availableSlots.map((slot, idx) => {
                      const isSelected = selectedSlot?.start_time === slot.start_time;
                      return (
                        <button
                          key={`${slot.start_time}-${idx}`}
                          type="button"
                          onClick={() => {
                            setSelectedSlot(slot);
                            setBookingError(null);
                          }}
                          disabled={isBooking}
                          className={`p-2.5 rounded-xl border text-left transition-all flex flex-col justify-between ${
                            isSelected
                              ? "border-sky-600 bg-sky-50 ring-2 ring-sky-500/20 shadow-sm"
                              : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/70"
                          }`}
                        >
                          <span
                            className={`text-xs font-bold ${
                              isSelected ? "text-sky-900" : "text-slate-800"
                            }`}
                          >
                            {formatTimeSlot(slot.start_time)}
                          </span>
                          <span
                            className={`text-[10px] mt-0.5 ${
                              isSelected ? "text-sky-700" : "text-slate-400"
                            }`}
                          >
                            to {formatTimeSlot(slot.end_time)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Error Banner */}
              {bookingError && (
                <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2.5 animate-in fade-in duration-150">
                  <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold">Booking Failed: </span>
                    <span>{bookingError}</span>
                  </div>
                </div>
              )}

              {/* Success Banner */}
              {bookingSuccess && (
                <div className="p-3.5 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2.5 animate-in fade-in duration-150">
                  <CheckCircle size={16} className="text-emerald-600 shrink-0" />
                  <span className="font-semibold">
                    Appointment confirmed! Redirecting to your appointments...
                  </span>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCloseSlotSelection}
                disabled={isBooking}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleConfirmBooking}
                disabled={!selectedSlot || isBooking || bookingSuccess}
                isLoading={isBooking}
                className="gap-2 font-semibold shadow-sm"
              >
                {isBooking ? "Securing Slot..." : "Confirm Booking"}
                {!isBooking && <ArrowRight size={14} />}
              </Button>
            </div>
          </div>
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
