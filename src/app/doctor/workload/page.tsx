"use client";

import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Clock,
  Users,
  CheckCircle2,
  TrendingUp,
  RefreshCw,
  AlertCircle,
  Calendar,
} from "lucide-react";
import { doctorService } from "@/services/doctors";
import { DoctorWorkload } from "@/types";

export default function DoctorWorkloadPage() {
  const [workload, setWorkload] = useState<DoctorWorkload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWorkload = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await doctorService.getWorkload();
      setWorkload(data);
    } catch (err: any) {
      console.error("Failed to load doctor workload:", err);
      setError(err?.message || "Failed to load clinical workload metrics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWorkload();
  }, []);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[360px] space-y-4">
        <RefreshCw className="h-8 w-8 text-teal-600 animate-spin" />
        <p className="text-sm text-slate-500 font-medium">Loading clinical workload metrics...</p>
      </div>
    );
  }

  if (error || !workload) {
    return (
      <div className="p-6 bg-red-50 border border-red-200 rounded-xl text-center space-y-4 max-w-lg mx-auto my-12">
        <div className="flex items-center justify-center space-x-2 text-red-700">
          <AlertCircle className="h-6 w-6" />
          <h3 className="font-semibold text-lg">Unable to Load Workload</h3>
        </div>
        <p className="text-sm text-red-600">
          {error || "An unexpected error occurred while fetching your practice workload."}
        </p>
        <button
          onClick={fetchWorkload}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-teal-600 hover:bg-teal-700 transition"
        >
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </button>
      </div>
    );
  }

  const stats = [
    {
      label: "Patients Completed Today",
      value: workload.patientsCompletedToday.toString(),
      icon: CheckCircle2,
      sub: workload.patientsCompletedToday > 0 ? "Documented in EHR" : "No encounters completed yet",
    },
    {
      label: "Active in Room / Waiting",
      value: workload.activeInRoomOrWaiting.toString(),
      icon: Users,
      sub: workload.activeInRoomOrWaiting > 0 ? "Queued for your clinic" : "Queue currently clear",
    },
    {
      label: "Mean Consult Duration",
      value: `${workload.meanConsultDurationMinutes} min`,
      icon: Clock,
      sub: workload.patientsCompletedToday > 0 ? "Calculated from completed sessions" : "Awaiting completed encounters",
    },
    {
      label: "Clinical Utilization",
      value: `${workload.clinicalUtilizationRate}%`,
      icon: TrendingUp,
      sub: "Active clinical care ratio",
    },
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Practice Operations
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Workload & Operational Pace
          </h1>
          <p className="text-sm text-slate-500">
            Daily consultation metrics, throughput pace, and room utilization.
          </p>
        </div>
        <button
          onClick={fetchWorkload}
          className="inline-flex items-center self-start sm:self-auto px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm"
        >
          <RefreshCw className="h-3.5 w-3.5 mr-1.5 text-teal-600" />
          Refresh Metrics
        </button>
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <Card key={idx} className="border-slate-200 bg-white shadow-sm">
              <CardContent className="p-4 space-y-1">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                    {stat.label}
                  </span>
                  <Icon size={16} className="text-teal-600" />
                </div>
                <p className="text-2xl font-bold text-slate-900 tabular-nums">
                  {stat.value}
                </p>
                <span className="text-[11px] text-slate-500 font-medium block">
                  {stat.sub}
                </span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Consultation Duration Distribution Table */}
      <Card className="border-slate-200 bg-white shadow-sm">
        <CardHeader className="pb-3 border-b border-slate-100">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Hourly Consultation Throughput (Today)
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          {workload.hourlyFlow.length === 0 ? (
            <div className="p-8 text-center text-slate-400 text-sm">
              <Calendar className="h-8 w-8 mx-auto mb-2 text-slate-300" />
              <p className="font-medium text-slate-600">No consultation encounters recorded today.</p>
              <p className="text-xs text-slate-400 mt-1">Throughput will populate dynamically as consultations are completed.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {workload.hourlyFlow.map((slot, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg border border-slate-100 bg-slate-50/70 flex items-center justify-between text-xs hover:bg-slate-50 transition"
                >
                  <div className="space-y-0.5">
                    <span className="font-bold text-slate-900 block text-sm">
                      {slot.hour}
                    </span>
                    <span className="text-slate-500">
                      Completed: {slot.count} {slot.count === 1 ? "patient" : "patients"}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                      Avg Consultation Time
                    </span>
                    <span className="font-bold text-slate-900 font-mono text-sm">
                      {slot.avgMinutes > 0 ? `${slot.avgMinutes} min / consult` : "N/A"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
