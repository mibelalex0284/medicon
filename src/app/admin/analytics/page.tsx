"use client";

import React, { useState } from "react";
import { analyticsService, CLINIC_DEPARTMENTS } from "@/services/analytics";
import {
  BarChart3,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Users,
  Activity,
  Calendar,
  Building2,
  Stethoscope,
  ArrowUpRight,
  ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function AdminAnalyticsPage() {
  const [timeRange, setTimeRange] = useState<"today" | "week" | "month">("today");
  const stats = analyticsService.getClinicAnalytics();
  const departments = analyticsService.getDepartmentStats();

  const hourlyData = [
    { hour: "08:00", arrivals: 6, completed: 4 },
    { hour: "09:00", arrivals: 12, completed: 8 },
    { hour: "10:00", arrivals: 18, completed: 14 },
    { hour: "11:00", arrivals: 15, completed: 13 },
    { hour: "12:00", arrivals: 8, completed: 9 },
    { hour: "13:00", arrivals: 5, completed: 6 },
    { hour: "14:00", arrivals: 11, completed: 10 },
    { hour: "15:00", arrivals: 9, completed: 8 },
    { hour: "16:00", arrivals: 4, completed: 5 },
  ];

  const maxHourly = Math.max(...hourlyData.map((h) => Math.max(h.arrivals, h.completed)));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <BarChart3 size={14} className="text-sky-600" />
            <span>Operational Intelligence</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1">
            Clinic Flow & Queue Analytics
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Key operational metrics, tail wait percentiles, doctor utilization rates, and SLA compliance.
          </p>
        </div>

        {/* Time Filter */}
        <div className="flex items-center bg-slate-200/80 p-1 rounded-xl text-xs font-medium">
          {(["today", "week", "month"] as const).map((range) => (
            <button
              key={range}
              onClick={() => setTimeRange(range)}
              className={cn(
                "px-3 py-1.5 rounded-lg capitalize transition-all",
                timeRange === range
                  ? "bg-white text-slate-900 shadow-xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              )}
            >
              {range === "today" ? "Today" : range === "week" ? "Past 7 Days" : "Past 30 Days"}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Mean Wait */}
        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Mean Wait Time
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <Clock size={16} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">{stats.meanWaitMinutes}</span>
            <span className="text-sm font-semibold text-slate-500">min</span>
          </div>
          <div className="mt-2 flex items-center gap-1.5 text-xs text-emerald-700">
            <ArrowUpRight size={13} className="rotate-45" />
            <span>4 min faster than last week</span>
          </div>
        </div>

        {/* P90 Tail Wait */}
        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              P90 Tail Wait
            </span>
            <div className="p-2 rounded-lg bg-sky-50 text-sky-600">
              <TrendingUp size={16} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">{stats.p90WaitMinutes}</span>
            <span className="text-sm font-semibold text-slate-500">min</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            90% of patients seen within 38 min (SLA: 45m)
          </p>
        </div>

        {/* Doctor Utilization */}
        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              Provider Utilization
            </span>
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Stethoscope size={16} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">{stats.doctorUtilizationRate}%</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Optimal workload range (80% - 90%)
          </p>
        </div>

        {/* Punctuality Rate */}
        <div className="bg-white p-5 rounded-xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">
              On-Time Punctuality
            </span>
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <CheckCircle2 size={16} />
            </div>
          </div>
          <div className="mt-3 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-700">{stats.punctualityRate}%</span>
          </div>
          <p className="mt-2 text-xs text-slate-500">
            Within 10 min of scheduled slot
          </p>
        </div>
      </div>

      {/* Hourly Flow Chart & Caseload Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Hourly Flow Graphic */}
        <div className="lg:col-span-2 bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="font-bold text-base text-slate-900">
                Hourly Patient Intake vs Consultations
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Arrival peak between 09:00 - 11:00 AM managed with staggered consultations.
              </p>
            </div>
            <div className="flex items-center gap-4 text-xs font-medium">
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-xs bg-sky-500" />
                <span className="text-slate-600">Arrivals</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-3 w-3 rounded-xs bg-emerald-500" />
                <span className="text-slate-600">Completed</span>
              </div>
            </div>
          </div>

          <div className="h-64 flex items-end justify-between gap-3 pt-6 pb-2 border-b border-slate-100">
            {hourlyData.map((item) => {
              const arrivalHeight = Math.round((item.arrivals / maxHourly) * 100);
              const completedHeight = Math.round((item.completed / maxHourly) * 100);
              return (
                <div key={item.hour} className="flex-1 flex flex-col items-center gap-1">
                  <div className="w-full flex items-end justify-center gap-1 h-48">
                    <div
                      style={{ height: `${arrivalHeight}%` }}
                      className="w-3 sm:w-5 bg-sky-500 rounded-t transition-all"
                      title={`${item.hour}: ${item.arrivals} Arrivals`}
                    />
                    <div
                      style={{ height: `${completedHeight}%` }}
                      className="w-3 sm:w-5 bg-emerald-500 rounded-t transition-all"
                      title={`${item.hour}: ${item.completed} Completed`}
                    />
                  </div>
                  <span className="text-[10px] font-mono text-slate-400 mt-2">
                    {item.hour.slice(0, 2)}h
                  </span>
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
            <span>Peak queue surge: 10:15 AM (18 active tokens)</span>
            <span className="font-medium text-slate-700">Throughput velocity: 11.2 pt/hr</span>
          </div>
        </div>

        {/* Urgent Delay & Quality Guardrails */}
        <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs flex flex-col justify-between">
          <div>
            <h3 className="font-bold text-base text-slate-900">
              Safety & SLA Guardrails
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Protocol adherence and critical queue divergence flags.
            </p>

            <div className="mt-5 space-y-4">
              <div>
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-700">Urgent Case Delay Rate</span>
                  <span className="text-emerald-700 font-bold">{stats.urgentDelayRate}% (Target &lt; 5%)</span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 mt-1.5 overflow-hidden">
                  <div
                    className="bg-emerald-500 h-2 rounded-full"
                    style={{ width: `${stats.urgentDelayRate * 10}%` }}
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Triage urgency level 2 cases routed to consultation within 15 min.
                </p>
              </div>

              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-700">SLA Wait Compliance</span>
                  <span className="text-sky-700 font-bold">94.8% (Target &gt; 90%)</span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 mt-1.5 overflow-hidden">
                  <div className="bg-sky-500 h-2 rounded-full" style={{ width: "94.8%" }} />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Patients called within their maximum initial uncertainty range estimate.
                </p>
              </div>

              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-700">Fact Confirmation Completion</span>
                  <span className="text-indigo-700 font-bold">98.1%</span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 mt-1.5 overflow-hidden">
                  <div className="bg-indigo-500 h-2 rounded-full" style={{ width: "98.1%" }} />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Intake fact sheets verified before doctor room entry.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-6 p-3 bg-sky-50/70 border border-sky-200/80 rounded-lg text-xs text-sky-900 flex items-start gap-2">
            <Activity size={15} className="text-sky-600 shrink-0 mt-0.5" />
            <span>
              <strong>Shift Recommendation:</strong> Consider adding 1 provider to Cardiovascular intake between 11:00 AM - 01:00 PM to mitigate ECG room backlog.
            </span>
          </div>
        </div>
      </div>

      {/* Department Breakdown Matrix */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-xs overflow-hidden">
        <div className="p-4 border-b border-slate-200/80 bg-slate-50/50">
          <h3 className="font-bold text-sm text-slate-900">
            Department Performance Breakdown
          </h3>
          <p className="text-xs text-slate-500">
            Current multi-wing throughput, queue depths, and localized bottlenecks.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs text-slate-600">
            <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200/80 uppercase text-[10px] tracking-wider">
              <tr>
                <th className="py-3 px-4">Department</th>
                <th className="py-3 px-4">Active Doctors</th>
                <th className="py-3 px-4">Total Waiting</th>
                <th className="py-3 px-4">Mean Wait</th>
                <th className="py-3 px-4">P90 Tail Wait</th>
                <th className="py-3 px-4">Urgent Caseload</th>
                <th className="py-3 px-4">Operational Status / Bottleneck</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {departments.map((dept) => (
                <tr key={dept.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-3.5 px-4 font-semibold text-slate-900">
                    {dept.name}
                  </td>
                  <td className="py-3.5 px-4">
                    <span className="font-medium text-slate-800">{dept.activeDoctors}</span>
                    <span className="text-slate-400 text-[11px]"> on duty</span>
                  </td>
                  <td className="py-3.5 px-4 font-bold text-slate-900">
                    {dept.totalWaiting}
                  </td>
                  <td className="py-3.5 px-4 font-medium text-slate-800">
                    {dept.meanWaitMinutes} min
                  </td>
                  <td className="py-3.5 px-4">
                    <span
                      className={cn(
                        "font-semibold",
                        dept.p90WaitMinutes > 45 ? "text-amber-600" : "text-slate-800"
                      )}
                    >
                      {dept.p90WaitMinutes} min
                    </span>
                  </td>
                  <td className="py-3.5 px-4">
                    {dept.urgentCasesCount > 0 ? (
                      <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 font-bold text-[10px]">
                        {dept.urgentCasesCount} Urgent
                      </span>
                    ) : (
                      <span className="text-slate-400 text-[11px]">None</span>
                    )}
                  </td>
                  <td className="py-3.5 px-4">
                    {dept.currentBottleneck ? (
                      <div className="flex items-center gap-1.5 text-amber-700 text-[11px] font-medium">
                        <AlertTriangle size={13} className="shrink-0" />
                        <span>{dept.currentBottleneck}</span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 text-emerald-700 text-[11px] font-medium">
                        <CheckCircle2 size={13} className="shrink-0" />
                        <span>Flow Nominal</span>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
