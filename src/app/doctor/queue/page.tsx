"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { queueService } from "@/services/queue";
import { consultationService } from "@/services/consultation";
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
} from "lucide-react";

export default function DoctorQueuePage() {
  const router = useRouter();
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [activeActionId, setActiveActionId] = useState<string | null>(null);

  useEffect(() => {
    setQueue(queueService.getDoctorQueue("doc_202"));

    const unsubscribe = queueService.subscribe((entries) => {
      setQueue(entries.filter((e) => e.doctorId === "doc_202"));
    });

    return () => unsubscribe();
  }, []);

  const handleCallPatient = (id: string) => {
    setActiveActionId(id);
    setTimeout(() => {
      queueService.callPatient(id);
      setActiveActionId(null);
    }, 250);
  };

  const handleStartConsultation = (entry: QueueEntry) => {
    setActiveActionId(entry.id);
    setTimeout(() => {
      queueService.startConsultation(entry.id);
      consultationService.startNewConsultation(
        entry.id,
        entry.patientId,
        entry.patientName,
        "doc_202",
        "Dr. Anita Menon, MD"
      );
      setActiveActionId(null);
      router.push("/doctor/consultation");
    }, 300);
  };

  const handleComplete = (id: string) => {
    setActiveActionId(id);
    setTimeout(() => {
      queueService.completeConsultation(id);
      setActiveActionId(null);
    }, 250);
  };

  const handleNoShow = (id: string) => {
    if (confirm("Confirm marking patient as No-Show? This updates clinic throughput audit logs.")) {
      setActiveActionId(id);
      setTimeout(() => {
        queueService.markNoShow(id);
        setActiveActionId(null);
      }, 250);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Operational Queue Station
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Room 204 Live Queue
          </h1>
          <p className="text-sm text-slate-500">
            Realtime outpatient management, patient paging, and consultation triage flow.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs bg-white border border-slate-200 px-3 py-1.5 rounded-lg text-slate-700 font-semibold font-mono">
            {queue.filter((q) => q.status !== "completed" && q.status !== "no_show").length} Patients in Active Queue
          </span>
        </div>
      </div>

      {/* QUEUE TABLE / CARD STREAM */}
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

                    {/* ACTIONS ENFORCING REAL CLINICAL QUEUE STATE MACHINE */}
                    <td className="py-3.5 px-4 text-right space-x-1.5">
                      {entry.status === "waiting" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleCallPatient(entry.id)}
                            isLoading={activeActionId === entry.id}
                            className="h-8 text-xs font-semibold gap-1 text-amber-800 border-amber-300 hover:bg-amber-50"
                          >
                            <PhoneCall size={12} />
                            Call
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleStartConsultation(entry)}
                            isLoading={activeActionId === entry.id}
                            className="h-8 text-xs font-semibold gap-1 bg-teal-700 hover:bg-teal-800"
                          >
                            <Play size={12} />
                            Start
                          </Button>
                          <button
                            onClick={() => handleNoShow(entry.id)}
                            title="Mark No-Show"
                            className="text-slate-400 hover:text-rose-600 p-1.5 align-middle rounded hover:bg-slate-100"
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
                            className="h-8 text-xs font-semibold gap-1 bg-teal-700 hover:bg-teal-800"
                          >
                            <Play size={12} />
                            Begin Consult
                          </Button>
                          <button
                            onClick={() => handleNoShow(entry.id)}
                            title="Mark No-Show"
                            className="text-slate-400 hover:text-rose-600 p-1.5 align-middle rounded hover:bg-slate-100"
                          >
                            <UserX size={14} />
                          </button>
                        </>
                      )}

                      {entry.status === "in_consultation" && (
                        <Button
                          size="sm"
                          onClick={() => handleComplete(entry.id)}
                          isLoading={activeActionId === entry.id}
                          className="h-8 text-xs font-semibold gap-1 bg-emerald-700 hover:bg-emerald-800"
                        >
                          <CheckCircle size={12} />
                          Complete
                        </Button>
                      )}

                      {entry.status === "completed" && (
                        <span className="text-[11px] text-slate-400 font-medium">
                          Completed at {entry.consultationEndTime}
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
    </div>
  );
}
