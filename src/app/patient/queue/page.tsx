"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { queueService } from "@/services/queue";
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
  Volume2,
  RefreshCw,
} from "lucide-react";

export default function PatientQueuePage() {
  const { user } = useAuth();
  const [activeQueue, setActiveQueue] = useState<QueueEntry | undefined>(undefined);
  const [allQueue, setAllQueue] = useState<QueueEntry[]>([]);
  const [isRealtimeConnected, setIsRealtimeConnected] = useState(true);
  const [recentNotification, setRecentNotification] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    // Initial load
    const current = queueService.getPatientActiveQueue(user.id);
    setActiveQueue(current);
    setAllQueue(queueService.getAllQueue());

    // Subscribe to realtime state transitions
    const unsubscribe = queueService.subscribe((entries) => {
      setAllQueue(entries);
      const userEntry = entries.find(
        (e) =>
          e.patientId === user.id &&
          ["waiting", "called", "in_consultation"].includes(e.status)
      );

      if (userEntry) {
        if (userEntry.status === "called") {
          setRecentNotification("⚠️ Room 204: Your token was just called! Please enter.");
        } else if (activeQueue && userEntry.positionAhead !== activeQueue.positionAhead) {
          setRecentNotification("Your queue position and estimated wait were updated.");
        }
        setActiveQueue(userEntry);
      } else {
        setActiveQueue(undefined);
      }
    });

    return () => unsubscribe();
  }, [user]);

  // Simulated toggle of connection status to showcase Section 33 requirements
  const toggleConnection = () => {
    setIsRealtimeConnected((prev) => !prev);
  };

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
          {isRealtimeConnected ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-600"></span>
              </span>
              <span className="text-slate-700 font-medium flex items-center gap-1.5">
                <Wifi size={13} className="text-emerald-600" />
                Live Realtime Sync Active
              </span>
            </>
          ) : (
            <>
              <WifiOff size={14} className="text-amber-600" />
              <span className="text-amber-800 font-medium">
                Connection paused — Displaying last synced state
              </span>
            </>
          )}
        </div>
        <button
          onClick={toggleConnection}
          className="text-[11px] text-slate-500 hover:text-slate-800 underline"
        >
          {isRealtimeConnected ? "Simulate Offline" : "Reconnect"}
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
      <Card className="border-2 border-sky-500 bg-linear-to-b from-sky-50/50 to-white shadow-lg overflow-hidden">
        <div className="bg-slate-900 text-white px-5 py-3 flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-widest text-sky-400 flex items-center gap-1.5">
            <Clock size={14} />
            Live Queue Station
          </span>
          <QueueStatusBadge status={activeQueue.status} />
        </div>

        <CardContent className="p-6 md:p-8 space-y-6">
          {/* Main Token Display */}
          <div className="flex flex-col items-center justify-center text-center space-y-2 py-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Your Queue Token
            </span>
            <QueueToken
              token={activeQueue.token}
              status={activeQueue.status}
              size="hero"
            />
            <p className="text-sm font-semibold text-slate-700 pt-1">
              {activeQueue.patientName} (You)
            </p>
          </div>

          {/* Core Metrics: Position Ahead & Estimated Wait Range */}
          <div className="grid grid-cols-2 gap-3.5">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 text-center space-y-1">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-center gap-1">
                <Users size={14} className="text-slate-400" />
                People Ahead
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
                Uncertainty-aware range
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

          {/* What to do right now */}
          <div className="p-4 rounded-xl bg-amber-50/80 border border-amber-200 text-xs text-amber-900 space-y-1">
            <span className="font-bold flex items-center gap-1.5 text-amber-950">
              <AlertCircle size={15} />
              What should I do right now?
            </span>
            <p className="leading-relaxed">
              {activeQueue.status === "called"
                ? "Your token has been called! Please proceed immediately into Room 204. Your physician is expecting you."
                : activeQueue.positionAhead <= 1
                ? "Please remain seated in the Waiting Lounge right outside Room 204. You are next to be called."
                : "You may visit the clinic pharmacy or rest in the main atrium. Your queue position will update live on this screen."}
            </p>
          </div>
        </CardContent>
      </Card>

      {/* LIVE CLINIC QUEUE PROGRESSION (Visual Order) */}
      <div className="space-y-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Clinic Queue Stream ({allQueue.length} Active)
        </h3>
        <div className="space-y-2">
          {allQueue.map((entry) => {
            const isMe = entry.patientId === user?.id;
            return (
              <div
                key={entry.id}
                className={`p-3.5 rounded-xl border transition-all flex items-center justify-between text-xs ${
                  isMe
                    ? "bg-sky-50 border-sky-300 ring-2 ring-sky-200 font-medium"
                    : "bg-white border-slate-200 text-slate-600"
                }`}
              >
                <div className="flex items-center gap-3">
                  <QueueToken
                    token={entry.token}
                    status={entry.status}
                    size="sm"
                  />
                  <div>
                    <span className="font-semibold text-slate-900 block">
                      {isMe ? `${entry.patientName} (You)` : `Patient ${entry.token}`}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {entry.chiefComplaint}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <WaitEstimate
                    min={entry.estimatedWaitMinutes.min}
                    max={entry.estimatedWaitMinutes.max}
                    size="sm"
                  />
                  <QueueStatusBadge status={entry.status} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
