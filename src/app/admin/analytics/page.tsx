"use client";

import React, { useState, useEffect, useCallback } from "react";
import { analyticsService } from "@/services/analytics";
import { ClinicAnalytics, DepartmentStats, HourlyThroughput } from "@/types";
import {
  BarChart3,
  TrendingUp,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Stethoscope,
  Activity,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export default function AdminAnalyticsPage() {
  const [stats, setStats] = useState<ClinicAnalytics | null>(null);
  const [departments, setDepartments] = useState<DepartmentStats[]>([]);
  const [hourlyData, setHourlyData] = useState<HourlyThroughput[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await analyticsService.getOverview();
      setStats(data.analytics);
      setDepartments(data.departments);
      setHourlyData(data.hourlyFlow);
    } catch (err: any) {
      setError(err.message || "Failed to load operational analytics.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[360px] space-y-3">
        <RefreshCw size={24} className="text-sky-600 animate-spin" />
        <p className="text-sm font-medium text-slate-500">Loading operational analytics...</p>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="p-6 rounded-2xl bg-white border border-rose-200 shadow-xs space-y-4 max-w-lg mx-auto text-center mt-12">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
          <AlertTriangle size={24} />
        </div>
        <div className="space-y-1">
          <h2 className="text-lg font-bold text-slate-900">Analytics Unavailable</h2>
          <p className="text-xs text-slate-500">{error || "Could not retrieve clinic metrics from backend."}</p>
        </div>
        <Button onClick={loadData} size="sm" className="gap-2 mx-auto">
          <RefreshCw size={14} />
          Retry Request
        </Button>
      </div>
    );
  }

  const maxHourly = Math.max(
    1,
    ...hourlyData.map((h) => Math.max(h.arrivals, h.completed))
  );

  const totalHourlyActivity = hourlyData.reduce(
    (acc, curr) => acc + curr.arrivals + curr.completed,
    0
  );

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

        <Button
          variant="outline"
          size="sm"
          onClick={loadData}
          className="gap-2 self-start md:self-auto text-xs"
        >
          <RefreshCw size={13} />
          Refresh Metrics
        </Button>
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
          <div className="mt-2 text-xs text-slate-500">
            Calculated from today's live patient encounters
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
            90% of patients seen within {stats.p90WaitMinutes} min (SLA: 45m)
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
            Active encounters relative to physician capacity
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
            Within 15 min of scheduled booking slot
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
                Hourly Patient Intake vs Consultations (Today)
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                Real arrivals vs completed consultations across active clinic hours.
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

          {totalHourlyActivity === 0 ? (
            <div className="h-56 flex flex-col items-center justify-center border border-dashed border-slate-200 rounded-lg text-slate-400 text-xs">
              <BarChart3 size={24} className="mb-2 text-slate-300" />
              <span>No patient check-ins or completed encounters recorded today yet.</span>
            </div>
          ) : (
            <div className="h-64 flex items-end justify-between gap-3 pt-6 pb-2 border-b border-slate-100">
              {hourlyData.map((item) => {
                const arrivalHeight = Math.round((item.arrivals / maxHourly) * 100);
                const completedHeight = Math.round((item.completed / maxHourly) * 100);
                return (
                  <div key={item.hour} className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full flex items-end justify-center gap-1 h-48">
                      <div
                        style={{ height: `${Math.max(4, arrivalHeight)}%` }}
                        className={`w-3 sm:w-5 rounded-t transition-all ${
                          item.arrivals > 0 ? "bg-sky-500" : "bg-slate-100"
                        }`}
                        title={`${item.hour}: ${item.arrivals} Arrivals`}
                      />
                      <div
                        style={{ height: `${Math.max(4, completedHeight)}%` }}
                        className={`w-3 sm:w-5 rounded-t transition-all ${
                          item.completed > 0 ? "bg-emerald-500" : "bg-slate-100"
                        }`}
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
          )}

          <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
            <span>Active queue: {stats.activeQueueCount} patients waiting</span>
            <span className="font-medium text-slate-700">Completed today: {stats.completedToday}</span>
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
                  <span
                    className={cn(
                      "font-bold",
                      stats.urgentDelayRate <= 5.0 ? "text-emerald-700" : "text-amber-700"
                    )}
                  >
                    {stats.urgentDelayRate}% (Target &lt; 5%)
                  </span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 mt-1.5 overflow-hidden">
                  <div
                    className={cn(
                      "h-2 rounded-full",
                      stats.urgentDelayRate <= 5.0 ? "bg-emerald-500" : "bg-amber-500"
                    )}
                    style={{ width: `${Math.min(100, stats.urgentDelayRate * 10)}%` }}
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Urgent and emergency cases called within 15 min threshold.
                </p>
              </div>

              <div className="pt-2 border-t border-slate-100">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-700">Punctuality Compliance</span>
                  <span className="text-sky-700 font-bold">{stats.punctualityRate}% (Target &gt; 90%)</span>
                </div>
                <div className="w-full bg-slate-100 rounded-full h-2 mt-1.5 overflow-hidden">
                  <div
                    className="bg-sky-500 h-2 rounded-full"
                    style={{ width: `${Math.min(100, stats.punctualityRate)}%` }}
                  />
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  Appointments checked in on schedule.
                </p>
              </div>
            </div>
          </div>

          <div className="mt-6 p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 flex items-start gap-2">
            <Activity size={15} className="text-sky-600 shrink-0 mt-0.5" />
            <span>
              <strong>Operations Status:</strong> Total of {stats.totalPatientsToday} patient
              {stats.totalPatientsToday === 1 ? "" : "s"} scheduled or checked in today across all active wings.
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
