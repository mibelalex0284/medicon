"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Clock,
  Users,
  CheckCircle2,
  TrendingUp,
  Activity,
  Calendar,
} from "lucide-react";

export default function DoctorWorkloadPage() {
  const stats = [
    { label: "Patients Completed Today", value: "11", icon: CheckCircle2, sub: "+2 ahead of target" },
    { label: "Active in Room / Waiting", value: "5", icon: Users, sub: "Normal volume" },
    { label: "Mean Consult Duration", value: "14.2 min", icon: Clock, sub: "Expected: 12–18 min" },
    { label: "Clinical Utilization", value: "89.4%", icon: TrendingUp, sub: "Optimal physician load" },
  ];

  const hourlyFlow = [
    { hour: "08:00 - 09:00", count: 3, avgMinutes: 13 },
    { hour: "09:00 - 10:00", count: 4, avgMinutes: 15 },
    { hour: "10:00 - 11:00", count: 3, avgMinutes: 16 },
    { hour: "11:00 - 12:00", count: 1, avgMinutes: 12 },
  ];

  return (
    <div className="space-y-6">
      <div className="border-b border-slate-200 pb-4">
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

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {stats.map((stat, idx) => {
          const Icon = stat.icon;
          return (
            <Card key={idx} className="border-slate-200 bg-white">
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
                <span className="text-[11px] text-emerald-600 font-medium block">
                  {stat.sub}
                </span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Consultation Duration Distribution Table */}
      <Card className="border-slate-200 bg-white">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold uppercase tracking-wider text-slate-700">
            Hourly Consultation Throughput (Today)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {hourlyFlow.map((slot, idx) => (
              <div
                key={idx}
                className="p-3 rounded-lg border border-slate-100 bg-slate-50/70 flex items-center justify-between text-xs"
              >
                <div className="space-y-0.5">
                  <span className="font-bold text-slate-900 block text-sm">
                    {slot.hour}
                  </span>
                  <span className="text-slate-500">
                    Completed: {slot.count} patients
                  </span>
                </div>
                <div className="text-right">
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                    Avg Consultation Time
                  </span>
                  <span className="font-bold text-slate-900 font-mono text-sm">
                    {slot.avgMinutes} min / consult
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
