"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { queueService, QueueApiError } from "@/services/queue";
import { doctorService, DoctorResponse } from "@/services/doctors";
import { QueueEntry } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { QueueStatusBadge, TriageUrgencyBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import {
  PhoneCall,
  Play,
  CheckCircle,
  UserX,
  Clock,
  MapPin,
  Stethoscope,
  RefreshCw,
  AlertTriangle,
  AlertCircle,
  RotateCcw,
  Activity,
  X,
} from "lucide-react";

export default function DoctorQueuePage() {
  const router = useRouter();
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [doctorProfile, setDoctorProfile] = useState<DoctorResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);

  const loadQueue = useCallback(async (isPolling: boolean = false) => {
    if (!isPolling) setIsLoading(true);
    setErrorMessage(null);

    try {
      const [queueData, docData] = await Promise.all([
        queueService.getDoctorQueue("me"),
        doctorProfile ? Promise.resolve(doctorProfile) : doctorService.getCurrentDoctor().catch(() => null),
      ]);
      setQueue(queueData);
      if (docData && !doctorProfile) {
        setDoctorProfile(docData);
      }
    } catch (err: unknown) {
      if (err instanceof QueueApiError) {
        if (err.status === 401 || err.status === 403) {
          setErrorMessage("Doctor authorization session expired. Please sign in again.");
        } else {
          setErrorMessage(err.message);
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Could not load doctor queue. Please check your connection.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [doctorProfile]);

  useEffect(() => {
    loadQueue();

    // Regular interval refresh
    const interval = setInterval(() => {
      if (typeof document !== "undefined" && !document.hidden && !activeActionId) {
        loadQueue(true);
      }
    }, 8000);

    return () => clearInterval(interval);
  }, [loadQueue, activeActionId]);

  const handleCallPatient = async (id: string) => {
    if (activeActionId) return; // Prevent duplicate rapid clicks
    setActiveActionId(id);
    setActionError(null);

    try {
      await queueService.callPatient(id);
      await loadQueue(true);
    } catch (err: unknown) {
      if (err instanceof QueueApiError) {
        setActionError(`Failed to call patient: ${err.message}`);
      } else if (err instanceof Error) {
        setActionError(err.message);
      } else {
        setActionError("Failed to call patient. Please try again.");
      }
    } finally {
      setActiveActionId(null);
    }
  };

  const handleStartConsultation = async (entry: QueueEntry) => {
    if (activeActionId) return;
    setActiveActionId(entry.id);
    setActionError(null);

    try {
      await queueService.startConsultation(entry.id);
      router.push(`/doctor/consultation?queue_entry_id=${encodeURIComponent(entry.id)}`);
    } catch (err: unknown) {
      if (err instanceof QueueApiError) {
        setActionError(`Failed to start consultation: ${err.message}`);
      } else if (err instanceof Error) {
        setActionError(err.message);
      } else {
        setActionError("Failed to start consultation. Please try again.");
      }
      setActiveActionId(null);
    }
  };

  const handleComplete = async (id: string) => {
    if (activeActionId) return;
    setActiveActionId(id);
    setActionError(null);

    try {
      await queueService.completeConsultation(id);
      await loadQueue(true);
    } catch (err: unknown) {
      if (err instanceof QueueApiError) {
        setActionError(`Failed to complete consultation: ${err.message}`);
      } else if (err instanceof Error) {
        setActionError(err.message);
      } else {
        setActionError("Failed to complete consultation. Please try again.");
      }
    } finally {
      setActiveActionId(null);
    }
  };

  const handleNoShow = async (id: string) => {
    if (activeActionId) return;
    if (confirm("Confirm marking patient as No-Show? This authoritatively updates clinic logs.")) {
      setActiveActionId(id);
      setActionError(null);

      try {
        await queueService.markNoShow(id);
        await loadQueue(true);
      } catch (err: unknown) {
        if (err instanceof QueueApiError) {
          setActionError(`Failed to mark no-show: ${err.message}`);
        } else if (err instanceof Error) {
          setActionError(err.message);
        } else {
          setActionError("Failed to mark no-show. Please try again.");
        }
      } finally {
        setActiveActionId(null);
      }
    }
  };

  const activeCount = queue.filter(
    (q) => q.status !== "completed" && q.status !== "no_show"
  ).length;

  const doctorName = doctorProfile?.profile?.full_name || "Doctor";
  const roomName = "Room 204";

  return (
    <div className="space-y-6">
      {/* Action Error Notice */}
      {actionError && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center justify-between gap-2 shadow-2xs animate-in fade-in">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-rose-600 shrink-0" />
            <span>{actionError}</span>
          </div>
          <button
            onClick={() => setActionError(null)}
            className="text-rose-500 hover:text-rose-700 p-1"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Operational Queue Station
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            {roomName} Live Queue
          </h1>
          <p className="text-sm text-slate-500">
            Realtime outpatient management, patient paging, and consultation triage flow for {doctorName}.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => loadQueue(false)}
            className="text-xs gap-1.5"
            disabled={isLoading}
          >
            <RefreshCw size={12} className={isLoading ? "animate-spin" : ""} />
            Refresh Queue
          </Button>
          <span className="text-xs bg-white border border-slate-200 px-3 py-1.5 rounded-lg text-slate-700 font-semibold font-mono">
            {activeCount} Patients in Active Queue
          </span>
        </div>
      </div>

      {/* LOADING STATE */}
      {isLoading ? (
        <div className="p-16 text-center space-y-3 bg-white rounded-xl border border-slate-200 shadow-xs">
          <Activity size={24} className="animate-spin text-teal-700 mx-auto" />
          <p className="text-sm font-medium text-slate-600">
            Loading clinic operational queue...
          </p>
        </div>
      ) : errorMessage ? (
        /* ERROR STATE */
        <div className="p-6 rounded-xl bg-white border border-rose-200 shadow-xs space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-rose-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-rose-900">
                Failed to Load Queue
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
            </div>
          </div>
          <div className="pt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => loadQueue(false)}
              className="gap-2 text-xs"
            >
              <RotateCcw size={14} />
              Retry Connection
            </Button>
          </div>
        </div>
      ) : queue.length === 0 ? (
        /* EMPTY QUEUE */
        <div className="p-16 text-center space-y-3 bg-white rounded-xl border border-dashed border-slate-300 shadow-xs">
          <CheckCircle size={32} className="text-teal-600 mx-auto" />
          <h3 className="text-base font-bold text-slate-800">
            Queue is Currently Empty
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            All registered patients have been served, or no patients have checked in for this clinical session yet.
          </p>
        </div>
      ) : (
        /* QUEUE TABLE */
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[10px]">
                  <th className="py-3 px-4">Order</th>
                  <th className="py-3 px-4">Token</th>
                  <th className="py-3 px-4">Patient Details</th>
                  <th className="py-3 px-4">Triage Urgency</th>
                  <th className="py-3 px-4">Chief Concern</th>
                  <th className="py-3 px-4">Est. Wait Range</th>
                  <th className="py-3 px-4">Queue Status</th>
                  <th className="py-3 px-4 text-right">Clinical Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {queue.map((entry, index) => {
                  const isCurrent = entry.status === "in_consultation";
                  const isCalled = entry.status === "called";
                  return (
                    <tr
                      key={entry.id}
                      className={`transition-colors ${
                        isCurrent
                          ? "bg-emerald-50/70 font-medium"
                          : isCalled
                          ? "bg-amber-50/70 font-medium"
                          : "hover:bg-slate-50/80"
                      }`}
                    >
                      <td className="py-3.5 px-4 font-mono text-slate-400">
                        #{index + 1}
                      </td>

                      <td className="py-3.5 px-4">
                        <QueueToken
                          token={entry.token}
                          status={entry.status}
                          size="md"
                        />
                      </td>

                      <td className="py-3.5 px-4 space-y-0.5">
                        <span className="font-bold text-slate-900 block text-sm">
                          {entry.patientName}
                        </span>
                        <span className="text-slate-500 text-[11px]">
                          Checked in {entry.checkInTime}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        <TriageUrgencyBadge urgency={entry.triageUrgency} />
                      </td>

                      <td className="py-3.5 px-4 text-slate-700 max-w-xs">
                        <p className="line-clamp-2 leading-relaxed">
                          {entry.chiefComplaint}
                        </p>
                      </td>

                      <td className="py-3.5 px-4">
                        <WaitEstimate
                          min={entry.estimatedWaitMinutes.min}
                          max={entry.estimatedWaitMinutes.max}
                          size="sm"
                        />
                      </td>

                      <td className="py-3.5 px-4">
                        <QueueStatusBadge status={entry.status} />
                      </td>

                      {/* CLINICAL ACTIONS */}
                      <td className="py-3.5 px-4 text-right space-x-1.5">
                        {entry.status === "waiting" && (
                          <>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleCallPatient(entry.id)}
                              isLoading={activeActionId === entry.id}
                              disabled={Boolean(activeActionId)}
                              className="h-8 text-xs font-semibold gap-1 text-amber-800 border-amber-300 hover:bg-amber-50"
                            >
                              <PhoneCall size={12} />
                              Call
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleStartConsultation(entry)}
                              isLoading={activeActionId === entry.id}
                              disabled={Boolean(activeActionId)}
                              className="h-8 text-xs font-semibold gap-1 bg-teal-700 hover:bg-teal-800"
                            >
                              <Play size={12} />
                              Start
                            </Button>
                            <button
                              onClick={() => handleNoShow(entry.id)}
                              title="Mark No-Show"
                              disabled={Boolean(activeActionId)}
                              className="text-slate-400 hover:text-rose-600 p-1.5 align-middle rounded hover:bg-slate-100 disabled:opacity-50"
                            >
                              <UserX size={14} />
                            </button>
                          </>
                        )}

                        {entry.status === "called" && (
                          <>
                            <Button
                              size="sm"
                              onClick={() => handleStartConsultation(entry)}
                              isLoading={activeActionId === entry.id}
                              disabled={Boolean(activeActionId)}
                              className="h-8 text-xs font-semibold gap-1 bg-teal-700 hover:bg-teal-800"
                            >
                              <Play size={12} />
                              Begin Consult
                            </Button>
                            <button
                              onClick={() => handleNoShow(entry.id)}
                              title="Mark No-Show"
                              disabled={Boolean(activeActionId)}
                              className="text-slate-400 hover:text-rose-600 p-1.5 align-middle rounded hover:bg-slate-100 disabled:opacity-50"
                            >
                              <UserX size={14} />
                            </button>
                          </>
                        )}

                        {entry.status === "in_consultation" && (
                          <div className="inline-flex items-center gap-1.5">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                router.push(
                                  `/doctor/consultation?queue_entry_id=${encodeURIComponent(
                                    entry.id
                                  )}`
                                )
                              }
                              className="h-8 text-xs font-semibold gap-1 text-teal-800 border-teal-300 bg-teal-50"
                            >
                              Resume
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => handleComplete(entry.id)}
                              isLoading={activeActionId === entry.id}
                              disabled={Boolean(activeActionId)}
                              className="h-8 text-xs font-semibold gap-1 bg-emerald-700 hover:bg-emerald-800"
                            >
                              <CheckCircle size={12} />
                              Complete
                            </Button>
                          </div>
                        )}

                        {entry.status === "completed" && (
                          <span className="text-[11px] text-slate-400 font-medium">
                            Completed at {entry.consultationEndTime || "—"}
                          </span>
                        )}

                        {entry.status === "no_show" && (
                          <span className="text-[11px] text-rose-500 font-medium">
                            Marked No-Show
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
