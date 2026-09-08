"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { appointmentService } from "@/services/appointments";
import { queueService } from "@/services/queue";
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
  Sparkles,
} from "lucide-react";

export default function PatientAppointmentsPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [checkingInId, setCheckingInId] = useState<string | null>(null);

  useEffect(() => {
    if (user) {
      setAppointments(appointmentService.getAppointmentsByPatient(user.id));
    }
  }, [user]);

  const handleCheckIn = (apt: Appointment) => {
    if (!user) return;
    setCheckingInId(apt.id);

    setTimeout(() => {
      appointmentService.updateAppointmentStatus(apt.id, "checked_in");
      queueService.checkInPatient(
        user.id,
        user.name,
        apt.doctorId,
        apt.doctorName,
        apt.reasonForVisit,
        apt.triageUrgency === "urgent" ? "urgent" : "routine"
      );
      setAppointments(appointmentService.getAppointmentsByPatient(user.id));
      setCheckingInId(null);
      router.push("/patient/queue");
    }, 450);
  };

  const upcoming = appointments.filter(
    (a) => a.status === "scheduled" || a.status === "checked_in"
  );
  const past = appointments.filter((a) => a.status === "completed");

  return (
    <div className="space-y-6">
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

      {/* UPCOMING APPOINTMENTS SECTION */}
      <div className="space-y-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-600 flex items-center gap-2">
          <Clock size={16} className="text-sky-600" />
          Upcoming & Active ({upcoming.length})
        </h2>

        {upcoming.length === 0 ? (
          <div className="p-8 text-center rounded-xl border border-dashed border-slate-300 bg-white">
            <p className="text-sm text-slate-500">No scheduled appointments.</p>
            <Link href="/patient/find-care" className="inline-block mt-3">
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
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                    <p className="text-slate-600 italic">
                      Reason for visit: &ldquo;{apt.reasonForVisit}&rdquo;
                    </p>

                    {apt.status === "scheduled" ? (
                      <Button
                        size="sm"
                        onClick={() => handleCheckIn(apt)}
                        isLoading={checkingInId === apt.id}
                        className="bg-emerald-600 hover:bg-emerald-700 font-semibold gap-1.5 shrink-0"
                      >
                        Check In for Live Queue
                        <ArrowRight size={14} />
                      </Button>
                    ) : (
                      <Link href="/patient/queue">
                        <Button size="sm" variant="outline" className="gap-1.5 shrink-0 text-sky-700 border-sky-300 bg-sky-50">
                          View Live Queue
                          <ArrowRight size={14} />
                        </Button>
                      </Link>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* PAST CONSULTATIONS */}
      {past.length > 0 && (
        <div className="space-y-3 pt-4">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-500">
            Completed Visits ({past.length})
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
                  <span>{apt.doctorSpecialty}</span>
                  <span className="text-slate-400 block mt-0.5">
                    {apt.date} · Completed
                  </span>
                </div>
                <AppointmentStatusBadge status={apt.status} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
