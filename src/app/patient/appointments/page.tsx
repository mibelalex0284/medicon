"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import {
  appointmentService,
  AppointmentApiError,
} from "@/services/appointments";
import { Appointment } from "@/types";
import { AppointmentStatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Calendar,
  Clock,
  MapPin,
  CheckCircle2,
  Plus,
  ArrowRight,
  Activity,
  AlertCircle,
  RotateCcw,
  XCircle,
  Ticket,
  X,
} from "lucide-react";

function PatientAppointmentsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();

  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Check-in state
  const [checkingInId, setCheckingInId] = useState<string | null>(null);
  const [checkInError, setCheckInError] = useState<string | null>(null);
  const [issuedTokenInfo, setIssuedTokenInfo] = useState<{
    tokenNumber: string;
    doctorName: string;
    timeSlot: string;
  } | null>(null);

  // Cancellation state
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [cancellationTarget, setCancellationTarget] = useState<Appointment | null>(null);
  const [cancelReason, setCancelReason] = useState<string>("");
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Newly booked banner
  const [showBookedBanner, setShowBookedBanner] = useState<boolean>(false);

  useEffect(() => {
    if (searchParams.get("booked") === "true") {
      setShowBookedBanner(true);
    }
  }, [searchParams]);

  const loadAppointments = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const data = await appointmentService.listAppointments();
      setAppointments(data);
    } catch (err: unknown) {
      if (err instanceof AppointmentApiError) {
        if (err.status === 401 || err.status === 403) {
          setErrorMessage(
            "Authentication expired or unauthorized. Please re-authenticate to view your appointment history."
          );
        } else {
          setErrorMessage(err.message);
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage(
          "Could not retrieve appointment history. Please check your network connection."
        );
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAppointments();
  }, [loadAppointments]);

  // Handle authoritative server check-in
  const handleCheckIn = async (apt: Appointment) => {
    if (checkingInId) return; // Prevent duplicate submission
    setCheckingInId(apt.id);
    setCheckInError(null);

    try {
      const queueEntry = await appointmentService.checkInAppointment(apt.id);
      setIssuedTokenInfo({
        tokenNumber: queueEntry.token_number,
        doctorName: apt.doctorName,
        timeSlot: apt.timeSlot,
      });

      // Refresh real appointments from backend to reflect checked-in status
      await loadAppointments();
    } catch (err: unknown) {
      if (err instanceof AppointmentApiError) {
        if (err.status === 400 && err.message.toLowerCase().includes("already checked in")) {
          setCheckInError("This appointment has already been checked in.");
          await loadAppointments();
        } else if (err.status === 400 && err.message.toLowerCase().includes("cannot check in")) {
          setCheckInError(err.message);
        } else if (err.status === 404) {
          setCheckInError("Appointment not found on server.");
        } else if (err.status === 403) {
          setCheckInError("You do not have authorization to check in to this appointment.");
        } else {
          setCheckInError(err.message);
        }
      } else if (err instanceof Error) {
        setCheckInError(err.message);
      } else {
        setCheckInError("Patient check-in failed. Please check your connection and try again.");
      }
    } finally {
      setCheckingInId(null);
    }
  };

  // Open cancellation confirmation
  const handleOpenCancelModal = (apt: Appointment) => {
    setCancellationTarget(apt);
    setCancelReason("Patient requested cancellation");
    setCancelError(null);
  };

  // Confirm authoritative cancellation
  const handleConfirmCancel = async () => {
    if (!cancellationTarget || cancellingId) return;
    setCancellingId(cancellationTarget.id);
    setCancelError(null);

    try {
      await appointmentService.cancelAppointment(
        cancellationTarget.id,
        cancelReason.trim() || undefined
      );

      setCancellationTarget(null);
      await loadAppointments();
    } catch (err: unknown) {
      if (err instanceof AppointmentApiError) {
        if (err.status === 400) {
          setCancelError(err.message);
        } else if (err.status === 403) {
          setCancelError("You do not have authorization to cancel this appointment.");
        } else if (err.status === 404) {
          setCancelError("Appointment not found on server.");
        } else {
          setCancelError(err.message);
        }
      } else if (err instanceof Error) {
        setCancelError(err.message);
      } else {
        setCancelError("Cancellation failed. Please check your network connection.");
      }
    } finally {
      setCancellingId(null);
    }
  };

  const upcoming = appointments.filter(
    (a) => a.status === "scheduled" || a.status === "checked_in"
  );
  const past = appointments.filter(
    (a) => a.status === "completed" || a.status === "cancelled" || a.status === "no_show"
  );

  return (
    <div className="space-y-6">
      {/* Booked Confirmation Banner */}
      {showBookedBanner && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-center justify-between text-xs animate-in fade-in duration-200">
          <div className="flex items-center gap-2.5">
            <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
            <span className="font-semibold">
              Appointment successfully booked with your physician. It is recorded on the clinical schedule.
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowBookedBanner(false)}
            className="text-emerald-700 hover:text-emerald-900 p-1"
            aria-label="Dismiss banner"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Check-In Error Banner */}
      {checkInError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between animate-in fade-in duration-200">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-rose-600 shrink-0" />
            <span>
              <strong>Check-in Notice:</strong> {checkInError}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setCheckInError(null)}
            className="text-rose-600 hover:text-rose-800 p-1"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            My Appointments
          </h1>
          <p className="text-sm text-slate-500">
            View scheduled consultations, check in on arrival, and view past care.
          </p>
        </div>
        <Link href="/patient/find-care">
          <Button size="sm" className="gap-1.5 font-semibold">
            <Plus size={16} />
            Book New Care
          </Button>
        </Link>
      </div>

      {/* LOADING STATE */}
      {isLoading ? (
        <div className="p-12 text-center space-y-3 bg-white rounded-2xl border border-slate-200 shadow-xs">
          <Activity size={24} className="animate-spin text-sky-600 mx-auto" />
          <p className="text-sm font-medium text-slate-600">
            Retrieving clinical appointments...
          </p>
        </div>
      ) : errorMessage ? (
        /* ERROR STATE */
        <div className="p-6 rounded-2xl bg-white border border-rose-200 shadow-xs space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-rose-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-rose-900">
                Failed to Load Appointments
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
            </div>
          </div>
          <div className="pt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={loadAppointments}
              className="gap-2 text-xs"
            >
              <RotateCcw size={14} />
              Retry
            </Button>
          </div>
        </div>
      ) : (
        /* UPCOMING APPOINTMENTS SECTION */
        <div className="space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-600 flex items-center gap-2">
            <Clock size={16} className="text-sky-600" />
            Upcoming & Active ({upcoming.length})
          </h2>

          {upcoming.length === 0 ? (
            <div className="p-8 text-center rounded-xl border border-dashed border-slate-300 bg-white space-y-3">
              <Calendar size={28} className="text-slate-400 mx-auto" />
              <div className="space-y-1">
                <p className="text-sm font-semibold text-slate-700">
                  No upcoming appointments scheduled
                </p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Complete symptom intake or select a recommended specialist to book a new consultation.
                </p>
              </div>
              <Link href="/patient/find-care" className="inline-block pt-1">
                <Button size="sm">Find Care & Schedule</Button>
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {upcoming.map((apt) => (
                <Card
                  key={apt.id}
                  className="border-slate-200 shadow-xs hover:border-slate-300 transition-all bg-white"
                >
                  <CardContent className="p-5 space-y-4">
                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-3 border-b border-slate-100">
                      <div>
                        <h3 className="text-lg font-bold text-slate-900">
                          {apt.doctorName}
                        </h3>
                        <p className="text-xs font-semibold text-sky-700">
                          {apt.doctorSpecialty}
                        </p>
                        <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
                          <MapPin size={12} className="text-slate-400" />
                          {apt.department}
                        </p>
                      </div>

                      <div className="flex sm:flex-col items-end gap-1.5">
                        <AppointmentStatusBadge status={apt.status} />
                        <div className="text-xs font-semibold text-slate-700 font-mono">
                          {apt.date} · {apt.timeSlot}
                        </div>
                        {apt.queueToken && (
                          <div className="text-[11px] font-mono font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                            Token: {apt.queueToken}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                      <p className="text-slate-600 italic">
                        Reason for visit: &ldquo;{apt.reasonForVisit}&rdquo;
                      </p>

                      <div className="flex items-center gap-2 shrink-0">
                        {apt.status === "scheduled" && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleOpenCancelModal(apt)}
                              className="text-rose-600 hover:text-rose-700 hover:bg-rose-50 border-rose-200"
                            >
                              Cancel
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleCheckIn(apt)}
                              isLoading={checkingInId === apt.id}
                              className="bg-emerald-600 hover:bg-emerald-700 font-semibold gap-1.5"
                            >
                              Check In for Live Queue
                              <ArrowRight size={14} />
                            </Button>
                          </>
                        )}

                        {apt.status === "checked_in" && (
                          <Link href="/patient/queue">
                            <Button
                              size="sm"
                              variant="outline"
                              className="gap-1.5 text-sky-700 border-sky-300 bg-sky-50"
                            >
                              View Live Queue
                              <ArrowRight size={14} />
                            </Button>
                          </Link>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* PAST / CANCELLED CONSULTATIONS */}
      {past.length > 0 && !isLoading && (
        <div className="space-y-3 pt-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500">
            Consultation History ({past.length})
          </h2>
          <div className="space-y-2">
            {past.map((apt) => (
              <div
                key={apt.id}
                className="p-4 rounded-xl border border-slate-200 bg-white/70 flex items-center justify-between text-xs text-slate-600"
              >
                <div>
                  <span className="font-semibold text-slate-900 block text-sm">
                    {apt.doctorName}
                  </span>
                  <span>{apt.doctorSpecialty} · {apt.department}</span>
                  <span className="text-slate-400 block mt-0.5">
                    {apt.date} · {apt.timeSlot}
                  </span>
                </div>
                <AppointmentStatusBadge status={apt.status} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AUTHORITATIVE TOKEN ISSUED MODAL */}
      {issuedTokenInfo && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-sm bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-center space-y-4">
            <div className="w-14 h-14 rounded-full bg-emerald-100 text-emerald-600 mx-auto flex items-center justify-center">
              <Ticket size={28} />
            </div>
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-slate-900">
                Checked In Successfully
              </h3>
              <p className="text-xs text-slate-500">
                Your queue position has been assigned by the outpatient reception system.
              </p>
            </div>

            <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 space-y-1">
              <span className="text-[10px] uppercase font-bold text-emerald-700 tracking-wider">
                Live Queue Token
              </span>
              <div className="text-3xl font-extrabold text-emerald-900 font-mono tracking-wider">
                {issuedTokenInfo.tokenNumber}
              </div>
              <p className="text-[11px] text-emerald-700 font-medium">
                {issuedTokenInfo.doctorName} · {issuedTokenInfo.timeSlot}
              </p>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <Button
                variant="outline"
                size="sm"
                className="w-1/2"
                onClick={() => setIssuedTokenInfo(null)}
              >
                Stay Here
              </Button>
              <Button
                size="sm"
                className="w-1/2 gap-1 font-semibold"
                onClick={() => {
                  setIssuedTokenInfo(null);
                  router.push("/patient/queue");
                }}
              >
                View Queue
                <ArrowRight size={14} />
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* CANCELLATION CONFIRMATION DIALOG */}
      {cancellationTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 space-y-4">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-rose-50 text-rose-600">
                  <XCircle size={22} />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    Cancel Appointment
                  </h3>
                  <p className="text-xs text-slate-500">
                    Release your consultation slot
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setCancellationTarget(null)}
                disabled={Boolean(cancellingId)}
                className="text-slate-400 hover:text-slate-600 p-1"
                aria-label="Close dialog"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl text-xs text-slate-700 space-y-1 border border-slate-100">
              <p>
                <strong>Doctor:</strong> {cancellationTarget.doctorName} (
                {cancellationTarget.doctorSpecialty})
              </p>
              <p>
                <strong>Date & Time:</strong> {cancellationTarget.date} at{" "}
                {cancellationTarget.timeSlot}
              </p>
            </div>

            <div className="space-y-1.5">
              <label className="block text-xs font-semibold text-slate-700">
                Reason for cancellation (optional):
              </label>
              <textarea
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                rows={2}
                disabled={Boolean(cancellingId)}
                className="w-full text-xs p-2.5 rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-rose-500"
                placeholder="E.g., Conflict, symptom resolved, rescheduling..."
              />
            </div>

            {cancelError && (
              <div className="p-3 rounded-lg bg-rose-50 text-rose-800 text-xs border border-rose-200 flex items-start gap-2">
                <AlertCircle size={14} className="text-rose-600 shrink-0 mt-0.5" />
                <span>{cancelError}</span>
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                disabled={Boolean(cancellingId)}
                onClick={() => setCancellationTarget(null)}
              >
                Keep Appointment
              </Button>
              <Button
                size="sm"
                disabled={Boolean(cancellingId)}
                isLoading={Boolean(cancellingId)}
                onClick={handleConfirmCancel}
                className="bg-rose-600 hover:bg-rose-700 font-semibold"
              >
                {cancellingId ? "Cancelling..." : "Confirm Cancellation"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PatientAppointmentsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-12 text-center space-y-3">
          <Activity size={20} className="animate-spin text-sky-600 mx-auto" />
          <p className="text-xs text-slate-500">Loading appointments...</p>
        </div>
      }
    >
      <PatientAppointmentsContent />
    </Suspense>
  );
}
