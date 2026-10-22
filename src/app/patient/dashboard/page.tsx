"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { queueService } from "@/services/queue";
import { appointmentService } from "@/services/appointments";
import { QueueEntry, Appointment } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Search,
  ArrowRight,
  Clock,
  Users,
  MapPin,
  CalendarCheck,
  CheckCircle2,
  Stethoscope,
  Sparkles,
} from "lucide-react";

export default function PatientDashboard() {
  const { user } = useAuth();
  const [activeQueue, setActiveQueue] = useState<QueueEntry | undefined>(undefined);
  const [upcomingApt, setUpcomingApt] = useState<Appointment | undefined>(undefined);
  const [isCheckingIn, setIsCheckingIn] = useState(false);

  useEffect(() => {
    if (!user) return;

    // Load active queue
    queueService
      .getPatientActiveQueue(user.id)
      .then((q) => setActiveQueue(q || undefined))
      .catch(() => {});

    // Load upcoming appointment
    appointmentService
      .getUpcomingAppointment(user.id)
      .then((apt) => setUpcomingApt(apt))
      .catch(() => {});

    // Subscribe to live queue changes using the patient-facing endpoint
    const unsubscribe = queueService.subscribePatient((entry) => {
      setActiveQueue(entry || undefined);
    });

    return () => unsubscribe();
  }, [user]);

  const handleCheckIn = async () => {
    if (!user || !upcomingApt) return;
    setIsCheckingIn(true);
    try {
      // Transition appointment to checked_in and enter queue
      await appointmentService.updateAppointmentStatus(upcomingApt.id, "checked_in");
      const entry = await queueService.getPatientActiveQueue(user.id);
      setActiveQueue(entry || undefined);
      const refreshed = await appointmentService.getUpcomingAppointment(user.id);
      setUpcomingApt(refreshed);
    } catch {
      // keep existing state on error
    } finally {
      setIsCheckingIn(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Dynamic Header */}
      <div>
        <span className="text-xs font-semibold text-sky-700 tracking-wider uppercase">
          Welcome back
        </span>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          {user?.name?.split(" ")[0] || "Sarah"}
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          CareRoute-X Smart Outpatient Navigator
        </p>
      </div>

      {/* ADAPTIVE PRIMARY SURFACE: What do I need to do right now? */}

      {/* STATE 1: ACTIVE QUEUE (Highest Priority State) */}
      {activeQueue && (
        <section
          aria-label="Active Queue Status"
          className="rounded-2xl border-2 border-sky-400 bg-linear-to-b from-sky-50/80 to-white p-5 md:p-6 shadow-md transition-all"
        >
          <div className="flex items-center justify-between pb-3 border-b border-sky-200/80 mb-4">
            <div className="flex items-center gap-2">
              <span className="relative flex h-3 w-3">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-sky-600"></span>
              </span>
              <h2 className="text-xs md:text-sm font-bold uppercase tracking-wider text-sky-900">
                You Are In The Live Queue
              </h2>
            </div>
            <span className="text-xs font-semibold text-sky-800 bg-sky-100 px-2.5 py-0.5 rounded-full capitalize">
              {activeQueue.status === "called"
                ? "Please Proceed to Room"
                : activeQueue.status === "in_consultation"
                ? "Consultation Active"
                : "Waiting Turn"}
            </span>
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-5">
            <div className="flex items-center gap-4">
              <QueueToken
                token={activeQueue.token}
                status={activeQueue.status}
                size="hero"
              />
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-slate-700 text-sm font-semibold">
                  <Stethoscope size={16} className="text-sky-600" />
                  {activeQueue.doctorName}
                </div>
                <div className="flex items-center gap-1.5 text-xs text-slate-500">
                  <MapPin size={13} className="text-slate-400" />
                  {activeQueue.roomNumber} · {activeQueue.department}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 p-3 bg-white rounded-xl border border-sky-100">
              <div>
                <span className="text-[11px] text-slate-500 flex items-center gap-1 font-medium">
                  <Users size={12} className="text-slate-400" />
                  People Ahead
                </span>
                <p className="text-xl font-bold text-slate-900 tabular-nums">
                  {activeQueue.positionAhead}{" "}
                  <span className="text-xs font-normal text-slate-500">
                    {activeQueue.positionAhead === 1 ? "person" : "people"}
                  </span>
                </p>
              </div>

              <div>
                <span className="text-[11px] text-slate-500 flex items-center gap-1 font-medium">
                  <Clock size={12} className="text-slate-400" />
                  Estimated Wait
                </span>
                <WaitEstimate
                  min={activeQueue.estimatedWaitMinutes.min}
                  max={activeQueue.estimatedWaitMinutes.max}
                  size="sm"
                  showIcon={false}
                />
              </div>
            </div>
          </div>

          <div className="mt-5 pt-4 border-t border-sky-100 flex flex-col sm:flex-row items-center justify-between gap-3">
            <p className="text-xs text-slate-600 font-medium text-center sm:text-left">
              {activeQueue.status === "called"
                ? "⚠️ Your token was called! Head to Room 204 immediately."
                : "You will receive an instant notification when your doctor is ready."}
            </p>
            <Link href="/patient/queue" className="w-full sm:w-auto">
              <Button size="md" className="w-full sm:w-auto font-semibold gap-1.5 shadow-sm">
                Open Live Queue View
                <ArrowRight size={16} />
              </Button>
            </Link>
          </div>
        </section>
      )}

      {/* STATE 2: UPCOMING APPOINTMENT (When not in active queue or has scheduled visit) */}
      {!activeQueue && upcomingApt && upcomingApt.status === "scheduled" && (
        <section
          aria-label="Upcoming Clinical Appointment"
          className="rounded-2xl border border-slate-200 bg-white p-5 md:p-6 shadow-sm space-y-4"
        >
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <CalendarCheck size={18} className="text-sky-600" />
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                Your Next Appointment
              </h2>
            </div>
            <span className="text-xs font-medium bg-emerald-50 text-emerald-700 px-2.5 py-0.5 rounded-full border border-emerald-200">
              Confirmed for {upcomingApt.date}
            </span>
          </div>

          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-1">
              <h3 className="text-lg font-bold text-slate-900">
                {upcomingApt.doctorName}
              </h3>
              <p className="text-xs text-slate-500 font-medium">
                {upcomingApt.doctorSpecialty} · {upcomingApt.department}
              </p>
              <p className="text-xs text-slate-600 pt-1 italic">
                Reason: &ldquo;{upcomingApt.reasonForVisit}&rdquo;
              </p>
            </div>

            <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 min-w-[170px] space-y-1 text-center md:text-right">
              <span className="text-[11px] text-slate-500 block uppercase tracking-wider font-semibold">
                Scheduled Slot
              </span>
              <p className="text-base font-bold text-slate-900 font-mono">
                {upcomingApt.timeSlot}
              </p>
              <span className="text-[11px] text-emerald-600 font-medium flex items-center justify-center md:justify-end gap-1">
                <CheckCircle2 size={12} />
                Online Check-in Open
              </span>
            </div>
          </div>

          <div className="pt-3 border-t border-slate-100 flex flex-col sm:flex-row items-center justify-between gap-3">
            <span className="text-xs text-slate-500">
              Arriving at the clinic? Check in to claim your live queue token.
            </span>
            <Button
              size="md"
              onClick={handleCheckIn}
              isLoading={isCheckingIn}
              className="w-full sm:w-auto bg-emerald-600 hover:bg-emerald-700 font-semibold gap-1.5"
            >
              Check In Now
              <ArrowRight size={16} />
            </Button>
          </div>
        </section>
      )}

      {/* STATE 3: NO ACTIVE CARE (Find Care Prompt) */}
      {!activeQueue && (!upcomingApt || upcomingApt.status === "completed") && (
        <section
          aria-label="Start Care Journey"
          className="rounded-2xl border border-sky-100 bg-linear-to-br from-sky-50 to-slate-50 p-6 md:p-8 space-y-4"
        >
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-sky-100 text-sky-800 text-xs font-semibold">
            <Sparkles size={14} />
            Guided Care Direction
          </div>

          <div className="max-w-xl space-y-2">
            <h2 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
              What brings you in today?
            </h2>
            <p className="text-sm text-slate-600 leading-relaxed">
              Describe your symptoms in your own words. CareRoute-X will guide you
              through a structured intake assessment and match you with the right
              physician.
            </p>
          </div>

          <div className="pt-2">
            <Link href="/patient/find-care">
              <Button size="lg" className="w-full sm:w-auto font-semibold gap-2 shadow-sm">
                <Search size={18} />
                Begin Guided Care Triage
              </Button>
            </Link>
          </div>
        </section>
      )}

      {/* SECONDARY USEFUL ACTIONS (Compact & Focused) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
        <Link href="/patient/find-care" className="group">
          <Card className="h-full hover:border-sky-300 hover:shadow-sm transition-all">
            <CardContent className="p-5 flex items-start gap-3.5">
              <div className="p-2.5 bg-sky-50 text-sky-700 rounded-xl group-hover:bg-sky-600 group-hover:text-white transition-colors">
                <Search size={20} />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900 group-hover:text-sky-700 transition-colors">
                  Find Care & Triage
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Structured clinical intake and explainable doctor matching.
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>

        <Link href="/patient/health" className="group">
          <Card className="h-full hover:border-teal-300 hover:shadow-sm transition-all">
            <CardContent className="p-5 flex items-start gap-3.5">
              <div className="p-2.5 bg-teal-50 text-teal-700 rounded-xl group-hover:bg-teal-700 group-hover:text-white transition-colors">
                <Stethoscope size={20} />
              </div>
              <div className="space-y-1">
                <h3 className="text-sm font-bold text-slate-900 group-hover:text-teal-700 transition-colors">
                  Grounded Health Guides
                </h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Evidence-based clinical guidelines with verified citations.
                </p>
              </div>
            </CardContent>
          </Card>
        </Link>
      </div>
    </div>
  );
}
