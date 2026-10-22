"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { queueService } from "@/services/queue";
import { consultationService } from "@/services/consultation";
import { QueueEntry, Consultation } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
import { TriageUrgencyBadge } from "@/components/common/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Users,
  Clock,
  ArrowRight,
  PhoneCall,
  Play,
  CheckCircle,
  FileText,
  AlertCircle,
  Calendar,
  Activity,
} from "lucide-react";

export default function DoctorDashboard() {
  const router = useRouter();
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [activeConsult, setActiveConsult] = useState<Consultation | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadData = async () => {
      try {
        const [q, consult] = await Promise.all([
          queueService.getDoctorQueue("me"),
          consultationService.getActiveConsultation("me"),
        ]);
        if (isMounted) {
          setQueue(q);
          setActiveConsult(consult);
        }
      } catch {
        // ignore on unmount
      }
    };

    loadData();

    const unsubscribe = queueService.subscribe((entries) => {
      if (isMounted) {
        setQueue(entries);
      }
    });

    return () => {
      isMounted = false;
      unsubscribe();
    };
  }, []);

  const waitingPatients = queue.filter((q) => q.status === "waiting");
  const calledPatient = queue.find((q) => q.status === "called");
  const inConsultationPatient = queue.find((q) => q.status === "in_consultation");

  // Next patient to act on: either currently called, or the first waiting patient
  const nextPatient = calledPatient || waitingPatients[0];

  const handleCallPatient = async (queueId: string) => {
    if (actionLoading) return;
    setActionLoading(queueId);
    try {
      await queueService.callPatient(queueId);
      const q = await queueService.getDoctorQueue("me");
      setQueue(q);
    } catch {
      // handle error
    } finally {
      setActionLoading(null);
    }
  };

  const handleStartConsultation = async (patient: QueueEntry) => {
    if (actionLoading) return;
    setActionLoading(patient.id);
    try {
      await queueService.startConsultation(patient.id);
      router.push(`/doctor/consultation?queue_entry_id=${encodeURIComponent(patient.id)}`);
    } catch {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. CLINICAL GREETING & OPERATIONAL CONTEXT */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-teal-700 uppercase tracking-wider">
            Room 204 · Adult Outpatient Clinic
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Good morning, Dr. Menon.
          </h1>
          <p className="text-sm font-semibold text-slate-700 mt-1">
            18 appointments ·{" "}
            <span className="text-sky-700 font-bold">
              {waitingPatients.length + (calledPatient ? 1 : 0)} waiting
            </span>{" "}
            ·{" "}
            <span className="text-emerald-700 font-bold">
              {inConsultationPatient ? "1 consultation active" : "0 in consult"}
            </span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link href="/doctor/queue">
            <Button variant="outline" size="sm" className="text-xs font-semibold">
              <Users size={14} className="mr-1" />
              Full Queue List
            </Button>
          </Link>
          {inConsultationPatient && (
            <Link href="/doctor/consultation">
              <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800 text-xs font-semibold">
                <Activity size={14} className="mr-1" />
                Resume Active Consult
              </Button>
            </Link>
          )}
        </div>
      </div>

      {/* 2. ACTIVE CONSULTATION IN PROGRESS (If any) */}
      {inConsultationPatient && (
        <section aria-label="Active Consultation Notice">
          <div className="p-4 rounded-xl bg-emerald-50 border-2 border-emerald-300 text-emerald-950 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
            <div className="flex items-center gap-3">
              <QueueToken
                token={inConsultationPatient.token}
                status="in_consultation"
                size="md"
              />
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-base text-emerald-950">
                    {inConsultationPatient.patientName}
                  </span>
                  <span className="text-xs text-emerald-800 font-medium">
                    (In Room 204 now)
                  </span>
                </div>
                <p className="text-xs text-emerald-800">
                  {inConsultationPatient.chiefComplaint}
                </p>
              </div>
            </div>

            <Link href="/doctor/consultation">
              <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800 gap-1.5 shrink-0">
                Open Clinical Notes & Complete
                <ArrowRight size={14} />
              </Button>
            </Link>
          </div>
        </section>
      )}

      {/* 3. NEXT PATIENT SPOTLIGHT: "Who needs me next?" */}
      <section aria-label="Next Patient Spotlight" className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
            <Clock size={14} className="text-teal-600" />
            Who Needs Me Next?
          </h2>
          <span className="text-xs text-slate-500">
            Current Queue Position 1
          </span>
        </div>

        {nextPatient ? (
          <Card className="border-2 border-slate-300 shadow-md bg-white overflow-hidden">
            <div className="p-6 space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="flex items-start gap-4">
                  <QueueToken
                    token={nextPatient.token}
                    status={nextPatient.status}
                    size="hero"
                  />
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-xl font-bold text-slate-900">
                        {nextPatient.patientName}
                      </h3>
                      {nextPatient.patientAge && (
                        <span className="text-xs text-slate-500">
                          {nextPatient.patientAge}y · {nextPatient.patientGender}
                        </span>
                      )}
                      <TriageUrgencyBadge urgency={nextPatient.triageUrgency} />
                    </div>
                    <p className="text-xs font-mono text-slate-500">
                      Checked in: {nextPatient.checkInTime}
                    </p>
                    <p className="text-xs text-slate-500">
                      Position in Queue:{" "}
                      <strong className="text-slate-800">
                        {nextPatient.positionAhead === 0 ? "Next" : `${nextPatient.positionAhead + 1}th`}
                      </strong>
                    </p>
                  </div>
                </div>

                <div className="text-left sm:text-right space-y-1">
                  <span className="text-[11px] text-slate-500 uppercase font-semibold block">
                    Estimated Wait Range
                  </span>
                  <WaitEstimate
                    min={nextPatient.estimatedWaitMinutes.min}
                    max={nextPatient.estimatedWaitMinutes.max}
                    size="md"
                  />
                </div>
              </div>

              {/* Triage / Reason for visit context */}
              <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1">
                <span className="font-bold text-slate-700 uppercase tracking-wider text-[10px] block">
                  Intake Chief Complaint:
                </span>
                <p className="text-slate-900 font-medium text-sm">
                  &ldquo;{nextPatient.chiefComplaint}&rdquo;
                </p>
              </div>

              {/* Primary Operational Action */}
              <div className="pt-2 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100">
                <span className="text-xs text-slate-500">
                  {nextPatient.status === "called"
                    ? "Patient was called to Room 204. Ready to begin intake."
                    : "Patient is in waiting lounge. Call into consultation room."}
                </span>

                <div className="flex items-center gap-2">
                  {nextPatient.status === "waiting" && (
                    <Button
                      size="md"
                      onClick={() => handleCallPatient(nextPatient.id)}
                      isLoading={actionLoading === nextPatient.id}
                      className="bg-amber-600 hover:bg-amber-700 font-semibold gap-1.5 shadow-xs"
                    >
                      <PhoneCall size={16} />
                      Call Patient to Room 204
                    </Button>
                  )}

                  <Button
                    size="md"
                    onClick={() => handleStartConsultation(nextPatient)}
                    isLoading={actionLoading === nextPatient.id}
                    className="bg-teal-700 hover:bg-teal-800 font-semibold gap-1.5 shadow-sm"
                  >
                    <Play size={16} />
                    Start Consultation
                  </Button>
                </div>
              </div>
            </div>
          </Card>
        ) : (
          <div className="p-8 text-center bg-white rounded-xl border border-slate-200">
            <CheckCircle size={32} className="text-emerald-600 mx-auto mb-2" />
            <h3 className="font-bold text-slate-800">Queue is Clear</h3>
            <p className="text-xs text-slate-500 mt-1">
              All waiting patients for Room 204 have completed consultations.
            </p>
          </div>
        )}
      </section>

      {/* 4. UPCOMING QUEUE PREVIEW TABLE (Dense & Usable) */}
      <section aria-label="Remaining Queue Preview" className="space-y-2 pt-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Next Patients In Line ({waitingPatients.length})
          </h2>
          <Link
            href="/doctor/queue"
            className="text-xs text-teal-700 hover:underline font-semibold"
          >
            Manage Queue Actions →
          </Link>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-2xs">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase font-semibold text-[10px]">
                <th className="py-2.5 px-4">Token</th>
                <th className="py-2.5 px-4">Patient Name</th>
                <th className="py-2.5 px-4">Triage Urgency</th>
                <th className="py-2.5 px-4">Reason for Visit</th>
                <th className="py-2.5 px-4">Est. Wait</th>
                <th className="py-2.5 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {waitingPatients.slice(0, 4).map((patient) => (
                <tr key={patient.id} className="hover:bg-slate-50/80 transition-colors">
                  <td className="py-3 px-4 font-mono font-bold text-slate-900">
                    <QueueToken token={patient.token} status={patient.status} size="sm" />
                  </td>
                  <td className="py-3 px-4 font-semibold text-slate-900">
                    {patient.patientName}
                  </td>
                  <td className="py-3 px-4">
                    <TriageUrgencyBadge urgency={patient.triageUrgency} />
                  </td>
                  <td className="py-3 px-4 text-slate-600 max-w-xs truncate">
                    {patient.chiefComplaint}
                  </td>
                  <td className="py-3 px-4">
                    <WaitEstimate
                      min={patient.estimatedWaitMinutes.min}
                      max={patient.estimatedWaitMinutes.max}
                      size="sm"
                    />
                  </td>
                  <td className="py-3 px-4 text-right">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleCallPatient(patient.id)}
                      className="h-7 text-xs"
                    >
                      Call
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
