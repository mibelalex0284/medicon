"use client";

import React, { useState } from "react";
import {
  Settings,
  Clock,
  AlertTriangle,
  ShieldCheck,
  Bell,
  Save,
  CheckCircle2,
  Building2,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function AdminSettingsPage() {
  const [openingTime, setOpeningTime] = useState("08:00");
  const [closingTime, setClosingTime] = useState("18:00");
  const [lunchBreakStart, setLunchBreakStart] = useState("12:30");
  const [lunchBreakEnd, setLunchBreakEnd] = useState("13:30");

  const [maxWaitWarningMins, setMaxWaitWarningMins] = useState(45);
  const [p90AlertThresholdMins, setP90AlertThresholdMins] = useState(50);
  const [emergencyAutoIntercept, setEmergencyAutoIntercept] = useState(true);
  const [mandatoryFactsConfirmation, setMandatoryFactsConfirmation] = useState(true);
  const [smsTokenAlerts, setSmsTokenAlerts] = useState(true);
  const [boardRefreshIntervalSec, setBoardRefreshIntervalSec] = useState(10);

  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (typeof window !== "undefined") {
      const config = {
        openingTime,
        closingTime,
        lunchBreakStart,
        lunchBreakEnd,
        maxWaitWarningMins,
        p90AlertThresholdMins,
        emergencyAutoIntercept,
        mandatoryFactsConfirmation,
        smsTokenAlerts,
        boardRefreshIntervalSec,
      };
      localStorage.setItem("careroute_clinic_settings", JSON.stringify(config));
    }
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3500);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Settings size={14} className="text-sky-600" />
            <span>Clinic Configuration</span>
          </div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 mt-1">
            System & Queue Threshold Settings
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            Configure clinic operating hours, triage safety protocols, and real-time queue escalation thresholds.
          </p>
        </div>

        <button
          onClick={handleSave}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold shadow-xs transition-colors self-start md:self-auto"
        >
          <Save size={15} />
          <span>Save Configurations</span>
        </button>
      </div>

      {savedSuccess && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs font-semibold text-emerald-800 flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
          <span>Clinic settings successfully updated across all queue engines.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Section 1: Operating Hours */}
        <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
            <div className="p-2 rounded-lg bg-sky-50 text-sky-600">
              <Clock size={16} />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900">
                Clinic Operating Schedule
              </h3>
              <p className="text-xs text-slate-500">
                Standard daily service hours across all 4 outpatient wings.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Clinic Open Time
              </label>
              <input
                type="time"
                value={openingTime}
                onChange={(e) => setOpeningTime(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Clinic Close Time
              </label>
              <input
                type="time"
                value={closingTime}
                onChange={(e) => setClosingTime(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Lunch Intermission Start
              </label>
              <input
                type="time"
                value={lunchBreakStart}
                onChange={(e) => setLunchBreakStart(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Lunch Intermission End
              </label>
              <input
                type="time"
                value={lunchBreakEnd}
                onChange={(e) => setLunchBreakEnd(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
              />
            </div>
          </div>
        </div>

        {/* Section 2: Queue Escalation & Thresholds */}
        <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
            <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
              <AlertTriangle size={16} />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900">
                Queue SLA & Escalation Thresholds
              </h3>
              <p className="text-xs text-slate-500">
                Define when bottlenecks trigger supervisor alerts and doctor queue notifications.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Maximum Wait Warning Threshold (Minutes)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="15"
                  max="120"
                  value={maxWaitWarningMins}
                  onChange={(e) => setMaxWaitWarningMins(parseInt(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
                />
                <span className="text-xs text-slate-500 font-mono">min</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Triggers visual warning when patient waits beyond this time.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                P90 Tail Alert Threshold (Minutes)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="20"
                  max="120"
                  value={p90AlertThresholdMins}
                  onChange={(e) => setP90AlertThresholdMins(parseInt(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
                />
                <span className="text-xs text-slate-500 font-mono">min</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Triggers automated alert when 90th percentile wait breaches SLA.
              </p>
            </div>
          </div>
        </div>

        {/* Section 3: Clinical Safety & Triage Protocols */}
        <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
            <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
              <ShieldCheck size={16} />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900">
                Clinical Safety & Triage Protocols
              </h3>
              <p className="text-xs text-slate-500">
                Governing clinical intake guardrails and red-flag escalation rules.
              </p>
            </div>
          </div>

          <div className="space-y-3 pt-2">
            <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={emergencyAutoIntercept}
                onChange={(e) => setEmergencyAutoIntercept(e.target.checked)}
                className="mt-0.5 rounded text-sky-600 focus:ring-sky-500 h-4 w-4"
              />
              <div>
                <p className="text-xs font-bold text-slate-900">
                  Automatic Red-Flag Emergency Intercept
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Immediately blocks outpatient queue intake and displays emergency contact instructions (911 / nearest ER) if life-threatening symptoms are detected.
                </p>
              </div>
            </label>

            <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={mandatoryFactsConfirmation}
                onChange={(e) => setMandatoryFactsConfirmation(e.target.checked)}
                className="mt-0.5 rounded text-sky-600 focus:ring-sky-500 h-4 w-4"
              />
              <div>
                <p className="text-xs font-bold text-slate-900">
                  Mandatory Facts Sheet Confirmation
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Requires patients to confirm symptom duration and medications before handing intake data to the attending doctor.
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* Section 4: Live Broadcaster & Notifications */}
        <div className="bg-white p-6 rounded-xl border border-slate-200/80 shadow-xs space-y-4">
          <div className="flex items-center gap-2.5 border-b border-slate-100 pb-3">
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Bell size={16} />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900">
                Broadcasting & Realtime Sync
              </h3>
              <p className="text-xs text-slate-500">
                Waiting room TV displays and patient notification triggers.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
            <label className="flex items-start gap-3 p-3 rounded-lg border border-slate-200 hover:bg-slate-50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                checked={smsTokenAlerts}
                onChange={(e) => setSmsTokenAlerts(e.target.checked)}
                className="mt-0.5 rounded text-sky-600 focus:ring-sky-500 h-4 w-4"
              />
              <div>
                <p className="text-xs font-bold text-slate-900">
                  SMS & Push Alerts on "Called"
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Send immediate mobile alert to patient when the doctor presses "Call Patient".
                </p>
              </div>
            </label>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Display Board Polling Frequency (Seconds)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="3"
                  max="60"
                  value={boardRefreshIntervalSec}
                  onChange={(e) => setBoardRefreshIntervalSec(parseInt(e.target.value))}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-xs text-slate-900 focus:outline-hidden focus:ring-2 focus:ring-sky-500"
                />
                <span className="text-xs text-slate-500 font-mono">sec</span>
              </div>
              <p className="text-[11px] text-slate-400 mt-1">
                Display boards update instantly on WebSocket broadcast with fallback poll.
              </p>
            </div>
          </div>
        </div>

        {/* Bottom Save Action */}
        <div className="flex items-center justify-end gap-3 pt-2">
          <button
            type="submit"
            className="px-5 py-2.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs shadow-sm transition-colors flex items-center gap-2"
          >
            <Save size={15} />
            <span>Save All Clinic Settings</span>
          </button>
        </div>
      </form>
    </div>
  );
}
