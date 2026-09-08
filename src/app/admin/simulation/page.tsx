"use client";

import React, { useState } from "react";
import { analyticsService } from "@/services/analytics";
import {
  Sliders,
  ShieldAlert,
  Activity,
  AlertTriangle,
  RotateCcw,
  TrendingUp,
  Clock,
  Stethoscope,
  Users,
  CheckCircle2,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function AdminSimulationPage() {
  // Scenario variables
  const [doctorCapacityChange, setDoctorCapacityChange] = useState<number>(0);
  const [consultationDurationAvg, setConsultationDurationAvg] = useState<number>(15);
  const [volumeMultiplier, setVolumeMultiplier] = useState<number>(1.0);

  // Live baseline for comparison
  const baseline = analyticsService.getClinicAnalytics();

  // Run the mathematical simulation model
  const simulationResult = analyticsService.runSimulation({
    doctorCapacityChange,
    consultationDurationAvg,
    appointmentVolumeMultiplier: volumeMultiplier,
  });

  const handleApplyPreset = (preset: {
    cap: number;
    duration: number;
    vol: number;
  }) => {
    setDoctorCapacityChange(preset.cap);
    setConsultationDurationAvg(preset.duration);
    setVolumeMultiplier(preset.vol);
  };

  const handleReset = () => {
    setDoctorCapacityChange(0);
    setConsultationDurationAvg(15);
    setVolumeMultiplier(1.0);
  };

  const meanDelta = simulationResult.projectedMeanWait - baseline.meanWaitMinutes;
  const p90Delta = simulationResult.projectedP90Wait - baseline.p90WaitMinutes;
  const utilDelta = simulationResult.projectedUtilization - baseline.doctorUtilizationRate;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Sliders size={14} className="text-sky-600" />
            <span>Mathematical Modeling</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1">
            Capacity & Flow Simulation Sandbox
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Model the impact of staffing adjustments, appointment surges, and consultation lengths on queue wait times.
          </p>
        </div>

        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold transition-colors self-start md:self-auto"
        >
          <RotateCcw size={14} />
          <span>Reset to Baseline</span>
        </button>
      </div>

      {/* MANDATORY PROMINENT ISOLATION BANNER */}
      <div className="p-4 rounded-xl bg-amber-50 border-2 border-amber-300/80 text-amber-950 flex items-start gap-3 shadow-xs">
        <div className="p-2 rounded-lg bg-amber-200/70 text-amber-800 shrink-0 mt-0.5">
          <ShieldAlert size={20} />
        </div>
        <div>
          <h4 className="font-bold text-sm tracking-tight text-amber-900">
            SIMULATION SANDBOX — STRICT AIR-GAPPED ISOLATION
          </h4>
          <p className="text-xs text-amber-800/90 mt-1 leading-relaxed">
            This module runs purely on mathematical queue projection algorithms. Adjusting these parameters
            <strong> does NOT modify live patient tokens, active wait rooms, or scheduled doctor rosters</strong>.
            Use this tool safely to test shift policies and prepare for surges.
          </p>
        </div>
      </div>

      {/* Quick Scenario Presets */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-xs">
        <p className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
          Quick Preset Stress Tests
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => handleApplyPreset({ cap: 0, duration: 15, vol: 1.3 })}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <Sparkles size={13} className="text-sky-600" />
            Surge: +30% Patient Volume
          </button>
          <button
            onClick={() => handleApplyPreset({ cap: -2, duration: 15, vol: 1.0 })}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <AlertTriangle size={13} className="text-amber-600" />
            Staff Shortage: -2 Providers
          </button>
          <button
            onClick={() => handleApplyPreset({ cap: 0, duration: 12, vol: 1.0 })}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <Clock size={13} className="text-emerald-600" />
            Rapid Intake: 12 min Avg Consult
          </button>
          <button
            onClick={() => handleApplyPreset({ cap: 2, duration: 15, vol: 1.25 })}
            className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <Activity size={13} className="text-indigo-600" />
            Surge Mitigation: +2 Doctors & +25% Volume
          </button>
        </div>
      </div>

      {/* Main Interactive Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Controls Column (5 cols) */}
        <div className="lg:col-span-5 bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs space-y-6">
          <div className="border-b border-slate-100 pb-3">
            <h3 className="font-bold text-base text-slate-900">
              Simulation Parameters
            </h3>
            <p className="text-xs text-slate-500">
              Slide values to observe systemic ripple effects across waiting rooms.
            </p>
          </div>

          {/* Parameter 1: Doctor Capacity */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700">Doctor Roster Adjustment</span>
              <span
                className={cn(
                  "font-bold font-mono px-2 py-0.5 rounded text-xs",
                  doctorCapacityChange > 0
                    ? "bg-emerald-100 text-emerald-800"
                    : doctorCapacityChange < 0
                    ? "bg-rose-100 text-rose-800"
                    : "bg-slate-100 text-slate-700"
                )}
              >
                {doctorCapacityChange > 0 ? `+${doctorCapacityChange}` : doctorCapacityChange}{" "}
                Doctors ({12 + doctorCapacityChange} Total)
              </span>
            </div>
            <input
              type="range"
              min="-3"
              max="3"
              step="1"
              value={doctorCapacityChange}
              onChange={(e) => setDoctorCapacityChange(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-sky-600"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>-3 (Severe deficit)</span>
              <span>Baseline (12 Drs)</span>
              <span>+3 (Expanded)</span>
            </div>
          </div>

          {/* Parameter 2: Avg Consultation Duration */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700">Avg Consultation Length</span>
              <span className="font-bold font-mono px-2 py-0.5 rounded bg-sky-100 text-sky-800 text-xs">
                {consultationDurationAvg} minutes
              </span>
            </div>
            <input
              type="range"
              min="10"
              max="30"
              step="1"
              value={consultationDurationAvg}
              onChange={(e) => setConsultationDurationAvg(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-sky-600"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>10m (Fast turnover)</span>
              <span>15m (Baseline)</span>
              <span>30m (High complexity)</span>
            </div>
          </div>

          {/* Parameter 3: Patient Intake Volume */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-700">Intake Volume Multiplier</span>
              <span className="font-bold font-mono px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 text-xs">
                {volumeMultiplier.toFixed(2)}x (~{Math.round(68 * volumeMultiplier)} patients)
              </span>
            </div>
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.05"
              value={volumeMultiplier}
              onChange={(e) => setVolumeMultiplier(parseFloat(e.target.value))}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-sky-600"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>0.5x (Slow day)</span>
              <span>1.0x (Normal)</span>
              <span>2.0x (200% Surge)</span>
            </div>
          </div>
        </div>

        {/* Projection Output Column (7 cols) */}
        <div className="lg:col-span-7 space-y-4">
          {/* Projected Outcomes Card */}
          <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="font-bold text-base text-slate-900">
                  Projected Operational Impact
                </h3>
                <p className="text-xs text-slate-500">
                  Mathematical outcome comparison against current live clinic baseline.
                </p>
              </div>

              {/* Risk Assessment Flag */}
              <div>
                <span
                  className={cn(
                    "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider",
                    simulationResult.riskAssessment === "low"
                      ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                      : simulationResult.riskAssessment === "moderate"
                      ? "bg-amber-100 text-amber-800 border border-amber-200"
                      : "bg-rose-100 text-rose-800 border border-rose-200"
                  )}
                >
                  {simulationResult.riskAssessment} Risk
                </span>
              </div>
            </div>

            {/* Metrics comparison grid */}
            <div className="grid grid-cols-2 gap-4 mt-5">
              {/* Projected Mean Wait */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  Projected Mean Wait
                </span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-slate-900">
                    {simulationResult.projectedMeanWait}
                  </span>
                  <span className="text-sm font-semibold text-slate-500">min</span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500">Baseline: 22m</span>
                  <span
                    className={cn(
                      "font-bold",
                      meanDelta > 0 ? "text-rose-600" : meanDelta < 0 ? "text-emerald-600" : "text-slate-500"
                    )}
                  >
                    ({meanDelta > 0 ? `+${meanDelta}` : meanDelta} min)
                  </span>
                </div>
              </div>

              {/* Projected P90 Wait */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  Projected P90 Tail Wait
                </span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-slate-900">
                    {simulationResult.projectedP90Wait}
                  </span>
                  <span className="text-sm font-semibold text-slate-500">min</span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500">Baseline: 38m</span>
                  <span
                    className={cn(
                      "font-bold",
                      p90Delta > 0 ? "text-rose-600" : p90Delta < 0 ? "text-emerald-600" : "text-slate-500"
                    )}
                  >
                    ({p90Delta > 0 ? `+${p90Delta}` : p90Delta} min)
                  </span>
                </div>
              </div>

              {/* Provider Utilization */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  Provider Utilization
                </span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-slate-900">
                    {simulationResult.projectedUtilization}%
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500">Baseline: 88.5%</span>
                  <span
                    className={cn(
                      "font-bold",
                      simulationResult.projectedUtilization > 95
                        ? "text-rose-600"
                        : "text-slate-600"
                    )}
                  >
                    {simulationResult.projectedUtilization > 95 ? "Overload Risk" : "Manageable"}
                  </span>
                </div>
              </div>

              {/* Urgent Delay Rate */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  Urgent Case Delay Rate
                </span>
                <div className="mt-2 flex items-baseline gap-2">
                  <span className="text-3xl font-extrabold text-slate-900">
                    {simulationResult.projectedUrgentDelay}%
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-1.5 text-xs">
                  <span className="text-slate-500">Target: &lt; 5.0%</span>
                  <span
                    className={cn(
                      "font-bold",
                      simulationResult.projectedUrgentDelay > 5
                        ? "text-rose-600"
                        : "text-emerald-600"
                    )}
                  >
                    {simulationResult.projectedUrgentDelay > 5 ? "Breaches SLA" : "Safe"}
                  </span>
                </div>
              </div>
            </div>

            {/* Qualitative Assessment */}
            <div className="mt-5 p-4 rounded-xl bg-sky-50/70 border border-sky-200/80 text-xs text-sky-950">
              <h5 className="font-bold flex items-center gap-1.5">
                <Activity size={15} className="text-sky-700" />
                Operational Analysis & Staffing Guidance
              </h5>
              <p className="mt-1.5 leading-relaxed text-sky-900">
                {simulationResult.riskAssessment === "low"
                  ? "At these parameters, clinic operations remain well within normal SLA boundaries. Tail wait time (P90) is under 45 minutes and urgent patient escalations will not experience meaningful delays."
                  : simulationResult.riskAssessment === "moderate"
                  ? "Elevated wait times projected. While urgent cases can still be prioritized, non-urgent patients will likely encounter queue times exceeding 40 minutes. Consider drafting a floating triage nurse or extending afternoon slots."
                  : "CRITICAL BOTTLEPRINT PROJECTED. Provider utilization exceeds safety thresholds and urgent case delay rates threaten clinical safety protocols. Immediate action required: recruit on-call relief physicians or throttle non-urgent walk-ins."}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
