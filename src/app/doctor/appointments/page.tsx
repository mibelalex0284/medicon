"use client";

import React, { useState, useEffect } from "react";
import { appointmentService } from "@/services/appointments";
import { Appointment } from "@/types";
import { AppointmentStatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Calendar, Clock, MapPin, Search } from "lucide-react";

export default function DoctorAppointmentsPage() {
  const [allAppointments, setAllAppointments] = useState<Appointment[]>([]);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    appointmentService
      .getAllAppointments()
      .then((data) => setAllAppointments(data))
      .catch(() => {});
  }, []);

  const filtered = allAppointments.filter((a) => {
    if (filter === "scheduled") return a.status === "scheduled";
    if (filter === "checked_in") return a.status === "checked_in";
    if (filter === "completed") return a.status === "completed";
    return true;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Clinical Schedule
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Today&apos;s Appointments
          </h1>
          <p className="text-sm text-slate-500">
            Outpatient booked roster for Dr. Anita Menon (Room 204).
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex gap-1.5 p-1 bg-white rounded-lg border border-slate-200 text-xs">
          {["all", "scheduled", "checked_in", "completed"].map((f) => (
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
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[10px]">
              <th className="py-3 px-4">Time Slot</th>
              <th className="py-3 px-4">Date</th>
              <th className="py-3 px-4">Patient / Reason</th>
              <th className="py-3 px-4">Department</th>
              <th className="py-3 px-4">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((apt) => (
              <tr key={apt.id} className="hover:bg-slate-50 transition-colors">
                <td className="py-3 px-4 font-mono font-bold text-slate-900">
                  {apt.timeSlot}
                </td>
                <td className="py-3 px-4 text-slate-600 font-medium">
                  {apt.date}
                </td>
                <td className="py-3 px-4 space-y-0.5">
                  <span className="font-bold text-slate-900 block">
                    {apt.patientId === "pat_101" ? "Sarah Jenkins (CRX-9281)" : `Patient (${apt.patientId})`}
                  </span>
                  <span className="text-slate-500 text-[11px]">
                    {apt.reasonForVisit}
                  </span>
                </td>
                <td className="py-3 px-4 text-slate-600">
                  {apt.department}
                </td>
                <td className="py-3 px-4">
                  <AppointmentStatusBadge status={apt.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
