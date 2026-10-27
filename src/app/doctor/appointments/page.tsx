"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { appointmentService } from "@/services/appointments";
import { queueService, QueueApiError } from "@/services/queue";
import { doctorService, DoctorResponse } from "@/services/doctors";
import { Appointment } from "@/types";
import { AppointmentStatusBadge, TriageUrgencyBadge } from "@/components/common/StatusBadge";
import { QueueToken } from "@/components/common/QueueToken";
import { Button } from "@/components/ui/button";
import {
  Calendar,
  Clock,
  Search,
  UserCheck,
  PhoneCall,
  Play,
  CheckCircle,
  FileText,
  RefreshCw,
  AlertCircle,
  X,
  Stethoscope,
  Activity,
} from "lucide-react";

export default function DoctorAppointmentsPage() {
  const router = useRouter();
  const [allAppointments, setAllAppointments] = useState<Appointment[]>([]);
  const [doctorProfile, setDoctorProfile] = useState<DoctorResponse | null>(null);
  const [filter, setFilter] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);

  const loadData = useCallback(async (quiet: boolean = false) => {
    if (!quiet) setIsLoading(true);
    try {
      const [appts, doc] = await Promise.all([
        appointmentService.getAllAppointments(),
        doctorProfile ? Promise.resolve(doctorProfile) : doctorService.getCurrentDoctor().catch(() => null),
      ]);
      setAllAppointments(appts);
      if (doc && !doctorProfile) {
        setDoctorProfile(doc);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setFeedbackMessage({ type: "error", text: err.message });
      }
    } finally {
      setIsLoading(false);
    }
  }, [doctorProfile]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle checking in an appointment
  const handleCheckIn = async (apt: Appointment) => {
    if (actionLoadingId) return;
    setActionLoadingId(apt.id);
    setFeedbackMessage(null);

    try {
      const queueEntry = await appointmentService.checkInAppointment(apt.id);
      setFeedbackMessage({
        type: "success",
        text: `Patient ${apt.patientName || "assigned to appointment"} checked in successfully! Token: ${queueEntry.token_number}`,
      });
      await loadData(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to check in patient.";
      setFeedbackMessage({ type: "error", text: msg });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Handle calling a checked-in patient
  const handleCallPatient = async (apt: Appointment) => {
    if (actionLoadingId || !apt.queueEntryId) return;
    setActionLoadingId(apt.id);
    setFeedbackMessage(null);

    try {
      await queueService.callPatient(apt.queueEntryId);
      setFeedbackMessage({
        type: "success",
        text: `Patient ${apt.patientName || "assigned"} called to station.`,
      });
      await loadData(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to call patient.";
      setFeedbackMessage({ type: "error", text: msg });
    } finally {
      setActionLoadingId(null);
    }
  };

  // Handle starting/continuing consultation
  const handleConsultationAction = async (apt: Appointment) => {
    if (actionLoadingId || !apt.queueEntryId) return;
    setActionLoadingId(apt.id);
    setFeedbackMessage(null);

    try {
      if (apt.status !== "in_consultation" && apt.status !== "completed") {
        await queueService.startConsultation(apt.queueEntryId);
      }
      router.push(`/doctor/consultation?queue_entry_id=${encodeURIComponent(apt.queueEntryId)}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to initiate consultation.";
      setFeedbackMessage({ type: "error", text: msg });
      setActionLoadingId(null);
    }
  };

  // Filter & Search logic
  const filtered = allAppointments.filter((a) => {
    if (filter === "scheduled" && a.status !== "scheduled") return false;
    if (filter === "checked_in" && a.status !== "checked_in") return false;
    if (filter === "in_consultation" && a.status !== "in_consultation") return false;
    if (filter === "completed" && a.status !== "completed") return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const patientMatch = (a.patientName || "").toLowerCase().includes(q);
      const reasonMatch = (a.reasonForVisit || "").toLowerCase().includes(q);
      const tokenMatch = (a.queueToken || "").toLowerCase().includes(q);
      const idMatch = a.id.toLowerCase().includes(q);
      return patientMatch || reasonMatch || tokenMatch || idMatch;
    }

    return true;
  });

  const doctorDisplayName = doctorProfile?.profile?.full_name || "your clinical station";

  return (
    <div className="space-y-6">
      {/* Feedback Banner */}
      {feedbackMessage && (
        <div
          className={`p-3.5 rounded-xl text-xs flex items-center justify-between gap-2 shadow-2xs animate-in fade-in ${
            feedbackMessage.type === "success"
              ? "bg-emerald-50 border border-emerald-200 text-emerald-800"
              : "bg-rose-50 border border-rose-200 text-rose-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedbackMessage.type === "success" ? (
              <CheckCircle size={16} className="text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle size={16} className="text-rose-600 shrink-0" />
            )}
            <span>{feedbackMessage.text}</span>
          </div>
          <button
            onClick={() => setFeedbackMessage(null)}
            className="text-slate-500 hover:text-slate-700 p-1"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Clinical Schedule & Roster
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Today&apos;s Appointments
          </h1>
          <p className="text-sm text-slate-500">
            Outpatient booked roster and patient check-in management for {doctorDisplayName}.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => loadData(false)}
            className="text-xs gap-1.5"
            disabled={isLoading}
          >
            <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} />
            Refresh
          </Button>
          <Button
            size="sm"
            onClick={() => router.push("/doctor/queue")}
            className="text-xs bg-teal-700 hover:bg-teal-800 text-white font-semibold gap-1.5"
          >
            <Activity size={14} />
            Live Queue Station
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5 p-1 bg-white rounded-lg border border-slate-200 text-xs">
          {["all", "scheduled", "checked_in", "in_consultation", "completed"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-md capitalize font-medium transition-colors ${
                filter === f
                  ? "bg-teal-700 text-white shadow-2xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              {f.replace("_", " ")}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-64">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search patient or reason..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full text-xs pl-8 pr-3 py-2 rounded-lg border border-slate-200 bg-white focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
        </div>
      </div>

      {/* Main Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        {isLoading ? (
          <div className="p-16 text-center space-y-3">
            <Activity size={24} className="animate-spin text-teal-700 mx-auto" />
            <p className="text-sm font-medium text-slate-600">
              Loading appointment roster...
            </p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-16 text-center space-y-3">
            <Calendar size={32} className="text-slate-300 mx-auto" />
            <h3 className="text-base font-bold text-slate-800">
              No Appointments Found
            </h3>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              {searchQuery
                ? `No appointment records matched "${searchQuery}".`
                : "No appointments match the selected filter category."}
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[10px]">
                  <th className="py-3 px-4">Time Slot</th>
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Patient Information</th>
                  <th className="py-3 px-4">Reason / Concern</th>
                  <th className="py-3 px-4">Token</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Workflow Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((apt) => {
                  const patientDisplayName =
                    apt.patientName || `Patient (${apt.patientId.slice(0, 8)})`;
                  const isRowActionLoading = actionLoadingId === apt.id;

                  return (
                    <tr key={apt.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3.5 px-4 font-mono font-bold text-slate-900">
                        {apt.timeSlot}
                      </td>
                      <td className="py-3.5 px-4 text-slate-600 font-medium whitespace-nowrap">
                        {apt.date}
                      </td>
                      <td className="py-3.5 px-4 space-y-0.5">
                        <span className="font-bold text-slate-900 block text-sm">
                          {patientDisplayName}
                        </span>
                        <span className="text-slate-400 text-[10px] font-mono block">
                          ID: {apt.patientId.slice(0, 12)}...
                        </span>
                      </td>
                      <td className="py-3.5 px-4 max-w-xs text-slate-700">
                        <p className="line-clamp-2 leading-relaxed">
                          {apt.reasonForVisit}
                        </p>
                      </td>
                      <td className="py-3.5 px-4">
                        {apt.queueToken ? (
                          <span className="inline-block px-2 py-0.5 rounded font-mono font-bold text-xs bg-teal-50 text-teal-800 border border-teal-200">
                            {apt.queueToken}
                          </span>
                        ) : (
                          <span className="text-slate-400 italic text-[11px]">—</span>
                        )}
                      </td>
                      <td className="py-3.5 px-4">
                        <AppointmentStatusBadge status={apt.status} />
                      </td>
                      <td className="py-3.5 px-4 text-right whitespace-nowrap">
                        {apt.status === "scheduled" && (
                          <Button
                            size="sm"
                            onClick={() => handleCheckIn(apt)}
                            isLoading={isRowActionLoading}
                            disabled={Boolean(actionLoadingId)}
                            className="h-8 text-xs font-semibold gap-1.5 bg-teal-700 hover:bg-teal-800 text-white"
                          >
                            <UserCheck size={13} />
                            Check In Patient
                          </Button>
                        )}

                        {apt.status === "checked_in" && (
                          <div className="inline-flex items-center gap-1.5">
                            {apt.queueEntryId && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => handleCallPatient(apt)}
                                isLoading={isRowActionLoading}
                                disabled={Boolean(actionLoadingId)}
                                className="h-8 text-xs font-semibold gap-1 text-amber-800 border-amber-300 hover:bg-amber-50"
                              >
                                <PhoneCall size={12} />
                                Call Patient
                              </Button>
                            )}
                            {apt.queueEntryId && (
                              <Button
                                size="sm"
                                onClick={() => handleConsultationAction(apt)}
                                isLoading={isRowActionLoading}
                                disabled={Boolean(actionLoadingId)}
                                className="h-8 text-xs font-semibold gap-1 bg-teal-700 hover:bg-teal-800 text-white"
                              >
                                <Play size={12} />
                                Start Consult
                              </Button>
                            )}
                          </div>
                        )}

                        {apt.status === "in_consultation" && (
                          <Button
                            size="sm"
                            onClick={() => handleConsultationAction(apt)}
                            isLoading={isRowActionLoading}
                            disabled={Boolean(actionLoadingId)}
                            className="h-8 text-xs font-semibold gap-1.5 bg-emerald-700 hover:bg-emerald-800 text-white"
                          >
                            <Stethoscope size={13} />
                            Continue Consult
                          </Button>
                        )}

                        {apt.status === "completed" && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() =>
                              apt.queueEntryId &&
                              router.push(
                                `/doctor/consultation?queue_entry_id=${encodeURIComponent(
                                  apt.queueEntryId
                                )}`
                              )
                            }
                            className="h-8 text-xs font-semibold gap-1 text-slate-700 border-slate-300 hover:bg-slate-50"
                          >
                            <FileText size={12} />
                            View Summary
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
