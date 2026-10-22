"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { queueService, QueueApiError } from "@/services/queue";
import { QueueEntry } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { QueueStatusBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Clock,
  Users,
  MapPin,
  CheckCircle2,
  AlertCircle,
  Wifi,
  WifiOff,
  Bell,
  Stethoscope,
  RotateCcw,
  Activity,
  ArrowRight,
} from "lucide-react";

function PatientQueueContent() {
  const { user } = useAuth();
  const [activeQueue, setActiveQueue] = useState<QueueEntry | undefined>(undefined);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [recentNotification, setRecentNotification] = useState<string | null>(null);
  const prevQueueRef = React.useRef<QueueEntry | undefined>(undefined);

  const loadQueueStatus = useCallback(async (isPolling: boolean = false) => {
    if (!isPolling) setIsLoading(true);
    else setIsRefreshing(true);
    setErrorMessage(null);

    try {
      const entry = await queueService.getPatientActiveQueue();
      if (entry) {
        const prev = prevQueueRef.current;
        if (entry.status === "called" && prev?.status !== "called") {
          setRecentNotification("⚠️ Room 204: Your token was just called! Please proceed into the consultation room.");
        } else if (prev && entry.positionAhead !== prev.positionAhead) {
          setRecentNotification(`Your queue position updated: ${entry.positionAhead} patient(s) ahead of you.`);
        }
        prevQueueRef.current = entry;
        setActiveQueue(entry);
      } else {
        prevQueueRef.current = undefined;
        setActiveQueue(undefined);
      }
    } catch (err: unknown) {
      if (err instanceof QueueApiError) {
        if (err.status === 401 || err.status === 403) {
          setErrorMessage("Authentication session expired. Please sign in again.");
        } else {
          setErrorMessage(err.message);
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Could not connect to live queue. Please check your network connection.");
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadQueueStatus();

    // Controlled polite polling every 10 seconds while tab is active
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && !document.hidden) {
        loadQueueStatus(true);
      }
    }, 10000);

    return () => clearInterval(interval);
  }, [loadQueueStatus]);

  if (isLoading) {
    return (
      <div className="max-w-xl mx-auto space-y-4 pt-12 text-center">
        <Activity size={28} className="animate-spin text-sky-600 mx-auto" />
        <h2 className="text-base font-bold text-slate-800">
          Syncing with Outpatient Queue...
        </h2>
        <p className="text-xs text-slate-500">
          Retrieving live status and waiting time estimates.
        </p>
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="max-w-xl mx-auto space-y-4 pt-6">
        <div className="p-6 rounded-2xl bg-white border border-rose-200 shadow-xs space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-rose-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-rose-900">
                Queue Sync Unavailable
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
            </div>
          </div>
          <div className="pt-2 flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => loadQueueStatus(false)}
              className="gap-2 text-xs"
            >
              <RotateCcw size={14} />
              Retry Connection
            </Button>
            <Link href="/patient/appointments">
              <Button size="sm" variant="ghost" className="text-xs text-slate-600">
                View Appointments
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (!activeQueue) {
    return (
      <div className="max-w-xl mx-auto space-y-6 pt-6 text-center">
        <div className="p-4 bg-sky-50 text-sky-700 rounded-full w-16 h-16 mx-auto flex items-center justify-center">
          <Clock size={32} />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-slate-900">
            No Active Queue Token
          </h1>
          <p className="text-sm text-slate-500 max-w-sm mx-auto leading-relaxed">
            You do not currently have an active outpatient token. If you have an
            upcoming appointment, check in on arrival to join the queue.
          </p>
        </div>
        <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
          <Link href="/patient/appointments">
            <Button variant="outline">View My Appointments</Button>
          </Link>
          <Link href="/patient/find-care">
            <Button>Find Care & Join Queue</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Realtime Connectivity Status Banner */}
      <div className="flex items-center justify-between px-3.5 py-2 rounded-xl bg-slate-100/90 border border-slate-200 text-xs">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-600"></span>
          </span>
          <span className="text-slate-700 font-medium flex items-center gap-1.5">
            <Wifi size={13} className="text-emerald-600" />
            Live Clinic Sync Active
          </span>
          {isRefreshing && (
            <span className="text-[10px] text-slate-400 font-mono animate-pulse">
              (refreshing...)
            </span>
          )}
        </div>
        <button
          onClick={() => loadQueueStatus(true)}
          className="text-[11px] text-sky-700 hover:text-sky-900 font-medium flex items-center gap-1"
        >
          <RotateCcw size={12} />
          Refresh Now
        </button>
      </div>

      {/* Dynamic Notification Message */}
      {recentNotification && (
        <div className="p-3.5 bg-sky-50 border border-sky-200 rounded-xl text-xs font-semibold text-sky-900 flex items-center justify-between gap-2 shadow-2xs animate-in fade-in">
          <span className="flex items-center gap-2">
            <Bell size={15} className="text-sky-600 shrink-0" />
            {recentNotification}
          </span>
          <button
            onClick={() => setRecentNotification(null)}
            className="text-slate-400 hover:text-slate-700 text-xs p-1"
          >
            ✕
          </button>
        </div>
      )}

      {/* SIGNATURE TOKEN HERO CARD */}
      <Card className="border-2 border-sky-500 bg-gradient-to-b from-sky-50/50 to-white shadow-lg overflow-hidden">
        <div className="bg-slate-900 text-white px-5 py-3 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-widest text-sky-400 flex items-center gap-1.5">
            <Clock size={14} />
            Live Outpatient Queue
          </span>
          <QueueStatusBadge status={activeQueue.status} />
        </div>

        <CardContent className="p-6 md:p-8 space-y-6">
          {/* Main Token Display */}
          <div className="flex flex-col items-center justify-center text-center space-y-2 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Your Assigned Token
            </span>
            <QueueToken
              token={activeQueue.token}
              status={activeQueue.status}
              size="hero"
            />
            <p className="text-sm font-semibold text-slate-700 pt-1">
              {user?.name || "Patient"}
            </p>
          </div>

          {/* Core Metrics: Position Ahead & Estimated Wait Range */}
          <div className="grid grid-cols-2 gap-3.5">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center space-y-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                <Users size={14} className="text-slate-400" />
                Patients Ahead
              </span>
              <p className="text-3xl font-black text-slate-900 tabular-nums">
                {activeQueue.positionAhead}
              </p>
              <span className="text-[11px] text-slate-500 block">
                {activeQueue.positionAhead === 0
                  ? "You are next in line"
                  : activeQueue.positionAhead === 1
                  ? "1 person ahead of you"
                  : `${activeQueue.positionAhead} patients ahead of you`}
              </span>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center space-y-1 flex flex-col justify-center items-center">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                <Clock size={14} className="text-slate-400" />
                Estimated Wait
              </span>
              <WaitEstimate
                min={activeQueue.estimatedWaitMinutes.min}
                max={activeQueue.estimatedWaitMinutes.max}
                size="lg"
                showIcon={false}
              />
              <span className="text-[11px] text-slate-500">
                Authoritative estimate
              </span>
            </div>
          </div>

          {/* Physician & Clinic Context */}
          <div className="p-4 rounded-xl bg-sky-50/70 border border-sky-100 flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-sky-600 text-white rounded-lg">
                <Stethoscope size={18} />
              </div>
              <div>
                <span className="font-bold text-slate-900 block text-sm">
                  {activeQueue.doctorName}
                </span>
                <span className="text-slate-600">
                  {activeQueue.department} · {activeQueue.roomNumber}
                </span>
              </div>
            </div>
            <div className="text-right">
              <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                Checked In At
              </span>
              <span className="font-semibold text-slate-800 font-mono">
                {activeQueue.checkInTime}
              </span>
            </div>
          </div>

          {/* Clinical Guidance / Instructions */}
          <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 text-xs text-amber-900 space-y-1">
            <span className="font-bold flex items-center gap-1.5 text-amber-950">
              <AlertCircle size={15} />
              What should I do right now?
            </span>
            <p className="leading-relaxed">
              {activeQueue.status === "called"
                ? "Your token has been called! Please proceed immediately into the consultation room. Your physician is ready for you."
                : activeQueue.status === "in_consultation"
                ? "Your consultation is currently in progress."
                : activeQueue.positionAhead <= 1
                ? "Please remain seated in the waiting lounge right outside your room. You are next to be called."
                : "Please stay near the outpatient waiting area. Your queue position and estimated wait will update live."}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function PatientQueuePage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-xl mx-auto p-12 text-center space-y-3">
          <Activity size={24} className="animate-spin text-sky-600 mx-auto" />
          <p className="text-xs text-slate-500">Loading queue...</p>
        </div>
      }
    >
      <PatientQueueContent />
    </Suspense>
  );
}
