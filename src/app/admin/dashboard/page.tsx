"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { analyticsService } from "@/services/analytics";
import { queueService } from "@/services/queue";
import { ClinicAnalytics, DepartmentStats, QueueEntry } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Users,
  Clock,
  AlertTriangle,
  Activity,
  CheckCircle2,
  TrendingUp,
  ArrowRight,
  ShieldCheck,
  Building2,
  Layers,
} from "lucide-react";

export default function AdminDashboard() {
  const analytics: ClinicAnalytics = analyticsService.getClinicAnalytics();
  const departments: DepartmentStats[] = analyticsService.getDepartmentStats();
  const [queueEntries, setQueueEntries] = useState<QueueEntry[]>([]);

  useEffect(() => {
    queueService.getAllQueue().then(setQueueEntries).catch(() => {});
  }, []);

  const isOperatingNormally = analytics.urgentDelayRate < 5.0 && analytics.meanWaitMinutes < 30;

  return (
    <div className="space-y-6">
      {/* 1. PRIMARY OPERATIONAL STATUS: Is the clinic operating normally? */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-sky-700 uppercase tracking-wider">
            Operational Health Overview
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Clinic Operations Command
          </h1>
          <p className="text-sm text-slate-500">
            Realtime outpatient flow, queue bottlenecks, and clinic utilization.
          </p>
        </div>

        {/* Normalcy Health Cue */}
        <div
          className={`px-4 py-2.5 rounded-xl border flex items-center gap-2.5 shadow-2xs ${
            isOperatingNormally
              ? "bg-emerald-50 border-emerald-300 text-emerald-950"
              : "bg-amber-50 border-amber-300 text-amber-950"
          }`}
        >
          {isOperatingNormally ? (
            <>
              <CheckCircle2 size={18} className="text-emerald-700" />
              <div>
                <span className="text-xs font-bold uppercase tracking-wider block">
                  Normal Operations
                </span>
                <span className="text-[11px] text-emerald-800">
                  All 4 departments within target wait thresholds
                </span>
              </div>
            </>
          ) : (
            <>
              <AlertTriangle size={18} className="text-amber-700" />
              <div>
                <span className="text-xs font-bold uppercase tracking-wider block">
                  Capacity Delays Detected
                </span>
                <span className="text-[11px] text-amber-800">
                  Cardiovascular Pavilion exceeding P90 threshold
                </span>
              </div>
            </>
          )}
        </div>
      </div>

      {/* 2. CORE OPERATIONAL METRICS ROW (Strictly meaningful metrics) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active In Queue
              </span>
              <Users size={16} className="text-sky-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {analytics.activeQueueCount}
            </p>
            <span className="text-[11px] text-slate-500 block">
              12 in active consultation · 25 waiting
            </span>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Mean / P90 Wait
              </span>
              <Clock size={16} className="text-slate-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {analytics.meanWaitMinutes} / {analytics.p90WaitMinutes}
              <span className="text-sm font-normal text-slate-500 ml-1">min</span>
            </p>
            <span className="text-[11px] text-emerald-600 font-medium block">
              Within 45 min target service SLA
            </span>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Urgent Delay Rate
              </span>
              <AlertTriangle size={16} className="text-amber-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {analytics.urgentDelayRate}%
            </p>
            <span className="text-[11px] text-emerald-600 font-medium block">
              Below 5% clinical escalation threshold
            </span>
          </CardContent>
        </Card>

        <Link href="/admin/doctors" className="block group">
          <Card className="border-slate-200 bg-white group-hover:border-sky-300 group-hover:shadow-xs transition-all">
            <CardContent className="p-4 space-y-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 group-hover:text-sky-700">
                  Doctor Directory
                </span>
                <TrendingUp size={16} className="text-teal-600" />
              </div>
              <p className="text-3xl font-black text-slate-900 tabular-nums">
                {analytics.doctorUtilizationRate}%
              </p>
              <span className="text-[11px] text-sky-600 font-medium block">
                Manage registered physicians →
              </span>
            </CardContent>
          </Card>
        </Link>
      </div>

      {/* 3. DEPARTMENT QUEUE STATUS & BOTTLENECKS */}
      <section aria-label="Department Outpatient Flow">
        <div className="flex items-center justify-between pb-2">
          <h2 className="text-sm font-bold uppercase tracking-wider text-slate-700 flex items-center gap-2">
            <Layers size={16} className="text-sky-600" />
            Active Department Outpatient Flow
          </h2>
          <Link
            href="/admin/queues"
            className="text-xs text-sky-700 hover:underline font-semibold"
          >
            Manage All Queues →
          </Link>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {departments.map((dept) => (
            <Card key={dept.id} className="border-slate-200 bg-white shadow-2xs">
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="text-base font-bold text-slate-900">
                      {dept.name}
                    </h3>
                    <p className="text-xs text-slate-500">
                      {dept.activeDoctors} Physicians On-Duty · {dept.totalWaiting} Waiting
                    </p>
                  </div>
                  <span className="text-xs font-mono font-bold bg-slate-100 text-slate-800 px-2.5 py-1 rounded-md">
                    Mean: {dept.meanWaitMinutes}m
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 text-xs pt-1 border-t border-slate-100">
                  <div className="p-2 bg-slate-50 rounded-lg">
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                      P90 Wait
                    </span>
                    <strong className="text-slate-900 font-mono">
                      {dept.p90WaitMinutes} min
                    </strong>
                  </div>
                  <div className="p-2 bg-slate-50 rounded-lg">
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                      Urgent Cases
                    </span>
                    <strong
                      className={
                        dept.urgentCasesCount > 0 ? "text-amber-700 font-bold" : "text-slate-700"
                      }
                    >
                      {dept.urgentCasesCount}
                    </strong>
                  </div>
                  <div className="p-2 bg-slate-50 rounded-lg">
                    <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                      Queue Load
                    </span>
                    <strong className="text-slate-800 font-mono">
                      {dept.totalWaiting} Patients
                    </strong>
                  </div>
                </div>

                {dept.currentBottleneck && (
                  <div className="p-2.5 rounded-lg bg-amber-50/80 border border-amber-200 text-amber-900 text-xs flex items-center gap-2">
                    <AlertTriangle size={14} className="text-amber-700 shrink-0" />
                    <span>Bottleneck: {dept.currentBottleneck}</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* 4. FAST SCENARIO ANALYSIS ENTRY */}
      <section className="p-5 rounded-2xl bg-linear-to-r from-slate-900 to-slate-800 text-white flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-md">
        <div className="space-y-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-sky-400 block">
            Operational Scenario Analysis
          </span>
          <h3 className="text-lg font-bold">
            Simulate Capacity Adjustments & Surge Scenarios
          </h3>
          <p className="text-xs text-slate-300">
            Model physician capacity changes and patient arrival spikes without affecting the live queue.
          </p>
        </div>

        <Link href="/admin/simulation">
          <Button size="md" className="bg-sky-600 hover:bg-sky-700 text-white font-semibold gap-2 shrink-0">
            Open Simulation Sandbox
            <ArrowRight size={16} />
          </Button>
        </Link>
      </section>
    </div>
  );
}
