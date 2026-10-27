"use client";

import React, { useState, useEffect } from "react";
import { queueService } from "@/services/queue";
import { analyticsService } from "@/services/analytics";
import { QueueEntry, DepartmentStats, ClinicAnalytics } from "@/types";
import {
  Layers,
  Search,
  Filter,
  AlertTriangle,
  Clock,
  UserCheck,
  Stethoscope,
  Building2,
  RefreshCw,
  TrendingUp,
  Activity,
  CheckCircle2,
} from "lucide-react";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { StatusBadge } from "@/components/common/StatusBadge";
import { cn } from "@/lib/utils";

export default function AdminQueuesPage() {
  const [selectedDeptId, setSelectedDeptId] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [searchQuery, setSearchQuery] = useState("");
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [departments, setDepartments] = useState<DepartmentStats[]>([]);
  const [analytics, setAnalytics] = useState<ClinicAnalytics | null>(null);

  useEffect(() => {
    analyticsService
      .getOverview()
      .then((data) => {
        setDepartments(data.departments);
        setAnalytics(data.analytics);
      })
      .catch(() => {});

    const unsubscribe = queueService.subscribe((entries) => {
      setQueue(entries);
    });
    return () => unsubscribe();
  }, []);

  const filteredEntries = queue.filter((entry) => {
    // Dept filter
    if (selectedDeptId !== "all") {
      const targetDept = departments.find((d) => d.id === selectedDeptId);
      if (
        targetDept &&
        !entry.department.toLowerCase().includes(targetDept.name.toLowerCase().slice(0, 10)) &&
        !entry.department.toLowerCase().includes(targetDept.id.replace("dep_", ""))
      ) {
        return false;
      }
    }

    // Status filter
    if (statusFilter === "active") {
      if (!["waiting", "called", "in_consultation"].includes(entry.status)) return false;
    } else if (statusFilter !== "all" && entry.status !== statusFilter) {
      return false;
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchToken = entry.token.toLowerCase().includes(q);
      const matchName = entry.patientName.toLowerCase().includes(q);
      const matchDoctor = entry.doctorName.toLowerCase().includes(q);
      if (!matchToken && !matchName && !matchDoctor) return false;
    }

    return true;
  });

  const activeCount = queue.filter((q) =>
    ["waiting", "called", "in_consultation"].includes(q.status)
  ).length;
  const urgentCount = queue.filter(
    (q) =>
      ["waiting", "called"].includes(q.status) &&
      (q.triageUrgency === "urgent" || q.triageUrgency === "emergency")
  ).length;

  const meanWait = analytics ? `${analytics.meanWaitMinutes} min` : "0 min";
  const p90Wait = analytics ? `${analytics.p90WaitMinutes} min` : "0 min";

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Layers size={14} className="text-sky-600" />
            <span>Central Orchestration</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1">
            Department Queues & Flow
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Real-time multisite token orchestration, doctor room allocations, and bottleneck surveillance.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-medium">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>Realtime Synchronized</span>
          </div>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Active Queue</p>
          <div className="flex items-baseline gap-2 mt-1">
            <p className="text-2xl font-bold text-slate-900">{activeCount}</p>
            <span className="text-xs text-slate-500">
              across {departments.length} department{departments.length === 1 ? "" : "s"}
            </span>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Urgent Pending</p>
          <div className="flex items-baseline gap-2 mt-1">
            <p className="text-2xl font-bold text-amber-600">{urgentCount}</p>
            <span className="text-xs text-amber-700">prioritized</span>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Mean Wait Time</p>
          <div className="flex items-baseline gap-2 mt-1">
            <p className="text-2xl font-bold text-slate-900">{meanWait}</p>
            <span className="text-xs text-emerald-600 font-medium">Within SLA</span>
          </div>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
          <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">P90 Tail Wait</p>
          <div className="flex items-baseline gap-2 mt-1">
            <p className="text-2xl font-bold text-slate-900">{p90Wait}</p>
            <span className="text-xs text-slate-500">Target &lt; 45m</span>
          </div>
        </div>
      </div>

      {/* Department Cards Overview */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {departments.map((dept) => {
          const isSelected = selectedDeptId === dept.id;
          return (
            <button
              key={dept.id}
              onClick={() => setSelectedDeptId(isSelected ? "all" : dept.id)}
              className={cn(
                "p-4 rounded-xl text-left transition-all border relative",
                isSelected
                  ? "bg-slate-900 text-white border-slate-900 shadow-md ring-2 ring-sky-500/50"
                  : "bg-white text-slate-900 border-slate-200/80 hover:border-slate-300 hover:shadow-xs"
              )}
            >
              <div className="flex items-start justify-between">
                <span
                  className={cn(
                    "text-[11px] font-bold uppercase tracking-wider",
                    isSelected ? "text-sky-300" : "text-slate-500"
                  )}
                >
                  {dept.id === "dep_adult_opd"
                    ? "OPD Clinic"
                    : dept.id === "dep_cardio"
                    ? "Cardiology"
                    : dept.id === "dep_ortho"
                    ? "Orthopedics"
                    : "Pediatrics"}
                </span>
                <span
                  className={cn(
                    "text-xs font-bold px-2 py-0.5 rounded-full",
                    isSelected ? "bg-slate-800 text-slate-200" : "bg-slate-100 text-slate-700"
                  )}
                >
                  {dept.activeDoctors} Drs
                </span>
              </div>

              <h4 className="font-semibold text-sm mt-1.5 leading-snug line-clamp-1">
                {dept.name}
              </h4>

              <div className="mt-3 flex items-center justify-between text-xs">
                <span className={isSelected ? "text-slate-300" : "text-slate-500"}>
                  Waiting:{" "}
                  <strong className={isSelected ? "text-white" : "text-slate-900"}>
                    {dept.totalWaiting}
                  </strong>
                </span>
                <span className={isSelected ? "text-slate-300" : "text-slate-500"}>
                  P90:{" "}
                  <strong className={isSelected ? "text-white" : "text-slate-900"}>
                    {dept.p90WaitMinutes}m
                  </strong>
                </span>
              </div>

              {dept.currentBottleneck && (
                <div
                  className={cn(
                    "mt-2.5 pt-2 border-t text-[11px] flex items-center gap-1.5",
                    isSelected
                      ? "border-slate-800 text-amber-300"
                      : "border-slate-100 text-amber-700"
                  )}
                >
                  <AlertTriangle size={12} className="shrink-0" />
                  <span className="truncate">{dept.currentBottleneck}</span>
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Main Queue Table & Controls */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden">
        {/* Filter Toolbar */}
        <div className="p-4 border-b border-slate-200/80 flex flex-col md:flex-row md:items-center md:justify-between gap-3 bg-slate-50/50">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                placeholder="Search token, patient, doctor..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-3 py-1.5 rounded-lg border border-slate-300 bg-white text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:ring-2 focus:ring-sky-500 w-56 md:w-64"
              />
            </div>

            {selectedDeptId !== "all" && (
              <button
                onClick={() => setSelectedDeptId("all")}
                className="text-xs text-sky-700 bg-sky-50 hover:bg-sky-100 px-2.5 py-1.5 rounded-lg border border-sky-200 font-medium"
              >
                Clear Department Filter ×
              </button>
            )}
          </div>

          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-slate-200/70 p-1 rounded-lg text-xs">
            {[
              { key: "active", label: "Active Live" },
              { key: "waiting", label: "Waiting" },
              { key: "called", label: "Called" },
              { key: "in_consultation", label: "In Consultation" },
              { key: "all", label: "All Records" },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setStatusFilter(tab.key)}
                className={cn(
                  "px-2.5 py-1 rounded-md font-medium transition-all text-xs",
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

        {/* Live Flow Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200/80 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-4">Token</th>
                <th className="py-3 px-4">Patient Details</th>
                <th className="py-3 px-4">Department & Doctor</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Wait Range</th>
                <th className="py-3 px-4">Triage Urgency</th>
                <th className="py-3 px-4">Check-In</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredEntries.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-400">
                    <p className="text-sm font-medium">No queue records match your filter criteria.</p>
                    <p className="text-xs text-slate-400 mt-1">Try resetting the status or department filters above.</p>
                  </td>
                </tr>
              ) : (
                filteredEntries.map((entry) => (
                  <tr key={entry.id} className="hover:bg-slate-50/80 transition-colors">
                    <td className="py-3.5 px-4 font-mono font-bold text-slate-900">
                      <QueueToken token={entry.token} size="sm" />
                    </td>

                    <td className="py-3.5 px-4">
                      <p className="font-semibold text-slate-900">{entry.patientName}</p>
                      <p className="text-[11px] text-slate-500">
                        {entry.patientAge}y · {entry.patientGender}
                      </p>
                      <p className="text-[11px] text-slate-500 line-clamp-1 mt-0.5" title={entry.chiefComplaint}>
                        {entry.chiefComplaint}
                      </p>
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 font-medium text-slate-800">
                        <Stethoscope size={13} className="text-sky-600 shrink-0" />
                        <span>{entry.doctorName}</span>
                      </div>
                      <p className="text-[11px] text-slate-500 mt-0.5">
                        {entry.department} · <span className="font-medium text-slate-700">{entry.roomNumber}</span>
                      </p>
                    </td>

                    <td className="py-3.5 px-4">
                      <StatusBadge status={entry.status} />
                    </td>

                    <td className="py-3.5 px-4">
                      {entry.status === "in_consultation" ? (
                        <span className="text-xs font-medium text-emerald-700 flex items-center gap-1">
                          <Activity size={13} />
                          Active Now
                        </span>
                      ) : entry.status === "completed" ? (
                        <span className="text-xs text-slate-400">Finished</span>
                      ) : (
                        <WaitEstimate
                          estimate={entry.estimatedWaitMinutes}
                          positionAhead={entry.positionAhead}
                          compact
                        />
                      )}
                    </td>

                    <td className="py-3.5 px-4">
                      <span
                        className={cn(
                          "px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider",
                          entry.triageUrgency === "urgent"
                            ? "bg-amber-100 text-amber-800 border border-amber-200"
                            : entry.triageUrgency === "emergency"
                            ? "bg-rose-100 text-rose-800 border border-rose-200"
                            : "bg-slate-100 text-slate-700"
                        )}
                      >
                        {entry.triageUrgency}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-slate-500 font-mono text-[11px]">
                      {entry.checkInTime}
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
