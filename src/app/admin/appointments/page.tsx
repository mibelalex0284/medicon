"use client";

import React, { useState, useEffect } from "react";
import { appointmentService } from "@/services/appointments";
import { Appointment } from "@/types";
import {
  Calendar,
  Search,
  CheckCircle2,
  Clock,
  UserCheck,
  Stethoscope,
  Filter,
  AlertCircle,
  Building2,
  Plus,
  RefreshCw,
} from "lucide-react";
import { AppointmentStatusBadge } from "@/components/common/StatusBadge";
import { cn } from "@/lib/utils";

export default function AdminAppointmentsPage() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  const fetchAppointments = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await appointmentService.getAllAppointments();
      setAppointments(data);
    } catch (err: any) {
      console.error("Failed to load appointments:", err);
      setError(err?.message || "Failed to load clinic appointments");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAppointments();
  }, []);

  const handleQuickCheckIn = async (apt: Appointment) => {
    try {
      await appointmentService.checkInAppointment(apt.id);
      const refreshed = await appointmentService.getAllAppointments();
      setAppointments(refreshed);
      setActionSuccessMessage(`Patient checked in & added to Dr. ${apt.doctorName}'s live queue!`);
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: any) {
      console.error("Check-in failed:", err);
      setActionSuccessMessage(`Check-in failed: ${err?.message || "Please try again."}`);
      setTimeout(() => setActionSuccessMessage(null), 5000);
    }
  };

  const handleCancelAppointment = async (id: string) => {
    try {
      await appointmentService.cancelAppointment(id);
      const refreshed = await appointmentService.getAllAppointments();
      setAppointments(refreshed);
      setActionSuccessMessage("Appointment marked as cancelled.");
      setTimeout(() => setActionSuccessMessage(null), 4000);
    } catch (err: any) {
      console.error("Cancellation failed:", err);
      setActionSuccessMessage(`Cancellation failed: ${err?.message || "Please try again."}`);
      setTimeout(() => setActionSuccessMessage(null), 5000);
    }
  };

  const todayIso = new Date().toISOString().slice(0, 10);

  const filteredAppointments = appointments.filter((apt) => {
    if (statusFilter !== "all" && apt.status !== statusFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchDoc = apt.doctorName.toLowerCase().includes(q);
      const matchPatient = (apt.patientName || "").toLowerCase().includes(q);
      const matchReason = apt.reasonForVisit.toLowerCase().includes(q);
      const matchDept = apt.department.toLowerCase().includes(q);
      if (!matchDoc && !matchPatient && !matchReason && !matchDept) return false;
    }
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Calendar size={14} className="text-sky-600" />
            <span>Master Scheduling</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1">
            Appointment Registry
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Enterprise schedule audits, intake arrivals, and on-demand check-in synchronization.
          </p>
        </div>
        <button
          onClick={fetchAppointments}
          className="inline-flex items-center self-start md:self-auto px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 transition shadow-xs"
        >
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1.5 text-sky-600", loading && "animate-spin")} />
          Refresh
        </button>
      </div>

      {actionSuccessMessage && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs font-semibold text-emerald-800 flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
          <span>{actionSuccessMessage}</span>
        </div>
      )}

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-red-600 shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={fetchAppointments}
            className="text-xs font-semibold text-red-800 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Today's Bookings</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">
            {appointments.filter((a) => a.appointmentDate === todayIso).length}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Checked In</p>
          <p className="text-2xl font-bold text-sky-600 mt-1">
            {appointments.filter((a) => a.status === "checked_in").length}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Scheduled (Upcoming)</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">
            {appointments.filter((a) => a.status === "scheduled").length}
          </p>
        </div>
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Completed</p>
          <p className="text-2xl font-bold text-emerald-600 mt-1">
            {appointments.filter((a) => a.status === "completed").length}
          </p>
        </div>
      </div>

      {/* Main Table Container */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden">
        {/* Controls toolbar */}
        <div className="p-4 border-b border-slate-200/80 flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-slate-50/50">
          <div className="relative">
            <Search
              size={15}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              type="text"
              placeholder="Search patient, doctor, department, symptom..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-sky-500 w-64 md:w-80"
            />
          </div>

          <div className="flex items-center gap-1 bg-slate-200/70 p-1 rounded-lg text-xs overflow-x-auto">
            {[
              { key: "all", label: "All Statuses" },
              { key: "scheduled", label: "Scheduled" },
              { key: "checked_in", label: "Checked In" },
              { key: "completed", label: "Completed" },
              { key: "cancelled", label: "Cancelled" },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setStatusFilter(tab.key)}
                className={cn(
                  "px-2.5 py-1 rounded-md font-medium transition-all text-xs whitespace-nowrap",
                  statusFilter === tab.key
                    ? "bg-white text-slate-900 shadow-xs"
                    : "text-slate-600 hover:text-slate-900"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        {/* Appointments Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200/80 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-4">Patient / ID</th>
                <th className="py-3 px-4">Date & Slot</th>
                <th className="py-3 px-4">Doctor & Department</th>
                <th className="py-3 px-4">Chief Concern</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Desk Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    <RefreshCw className="h-6 w-6 text-sky-600 animate-spin mx-auto mb-2" />
                    <p className="text-xs">Loading appointment records...</p>
                  </td>
                </tr>
              ) : filteredAppointments.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-slate-400">
                    <p className="text-sm font-medium">No appointments match your filters.</p>
                  </td>
                </tr>
              ) : (
                filteredAppointments.map((apt) => (
                  <tr key={apt.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-slate-700">
                      <p className="font-semibold text-slate-900">
                        {apt.patientName || `Patient (${apt.patientId.slice(0, 8)})`}
                      </p>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {apt.id.slice(0, 8)}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      <p className="font-semibold text-slate-900">{apt.date}</p>
                      <p className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                        <Clock size={12} className="text-sky-600" />
                        {apt.timeSlot}
                      </p>
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 font-medium text-slate-900">
                        <Stethoscope size={13} className="text-sky-600 shrink-0" />
                        <span>{apt.doctorName}</span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {apt.department}
                      </p>
                    </td>

                    <td className="py-3.5 px-4 max-w-xs">
                      <p className="text-slate-800 line-clamp-1">{apt.reasonForVisit}</p>
                      <span
                        className={cn(
                          "inline-block mt-1 px-1.5 py-0.2 rounded text-[10px] uppercase font-bold",
                          apt.triageUrgency === "urgent"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-slate-100 text-slate-600"
                        )}
                      >
                        {apt.triageUrgency}
                      </span>
                    </td>

                    <td className="py-3.5 px-4">
                      <AppointmentStatusBadge status={apt.status} />
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      {apt.status === "scheduled" && (
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => handleQuickCheckIn(apt)}
                            className="px-2.5 py-1 rounded-md bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs shadow-xs transition-colors"
                          >
                            Check-In Patient
                          </button>
                          <button
                            onClick={() => handleCancelAppointment(apt.id)}
                            className="px-2 py-1 rounded-md border border-slate-300 text-slate-600 hover:bg-slate-100 text-xs"
                          >
                            Cancel
                          </button>
                        </div>
                      )}
                      {apt.status === "checked_in" && (
                        <span className="text-[11px] font-semibold text-sky-700 bg-sky-50 px-2 py-0.5 rounded border border-sky-200">
                          In Active Queue
                        </span>
                      )}
                      {apt.status === "completed" && (
                        <span className="text-[11px] text-slate-400">
                          Encounter Closed
                        </span>
                      )}
                      {apt.status === "cancelled" && (
                        <span className="text-[11px] text-rose-500">
                          Cancelled
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
