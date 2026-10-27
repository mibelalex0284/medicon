"use client";

import React, { useState, useEffect, Suspense, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { consultationService } from "@/services/consultation";
import { queueService } from "@/services/queue";
import { triageService, PreConsultationReportResponse } from "@/services/triage";
import { Consultation } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Clock,
  CheckCircle,
  FileText,
  Pill,
  User,
  ShieldCheck,
  AlertCircle,
  ArrowLeft,
  Save,
  Plus,
  Trash2,
  Lock,
  RotateCcw,
  Activity,
  CalendarCheck,
} from "lucide-react";

function DoctorConsultationInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queueEntryId = searchParams.get("queue_entry_id");
  const sessionId = searchParams.get("session_id") || searchParams.get("triage_session_id");

  const [consultation, setConsultation] = useState<Consultation | null>(null);
  const [preConsultationReport, setPreConsultationReport] = useState<PreConsultationReportResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  // Clinical form state
  const [notes, setNotes] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [newRx, setNewRx] = useState("");
  const [prescriptions, setPrescriptions] = useState<string[]>([]);

  // Action loading states
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);

  // Load authoritative consultation data
  const loadConsultationData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      let active: Consultation | null = null;

      if (queueEntryId) {
        // First try to fetch existing consultation for this queue entry
        active = await consultationService.getConsultationByQueueEntry(queueEntryId);

        // If not started yet, start or resume it idempotently
        if (!active) {
          active = await consultationService.startNewConsultation(queueEntryId);
        }
      } else {
        // Fallback to currently active consultation
        active = await consultationService.getActiveConsultation("me");
      }

      if (active) {
        setConsultation(active);
        setElapsedSeconds(active.elapsedSeconds || 0);
        setNotes(active.clinicalNotes || "");
        setDiagnosis(active.diagnosis || "");
        setPrescriptions(active.prescriptions || []);
        setFollowUp(active.followUpRecommendation || "");
      } else {
        setConsultation(null);
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to load clinical consultation record.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [queueEntryId]);

  useEffect(() => {
    loadConsultationData();

    if (sessionId) {
      triageService
        .getPreConsultationReport(sessionId)
        .then((report) => setPreConsultationReport(report))
        .catch((err) => {
          console.warn("Could not fetch pre-consultation report:", err);
        });
    }
  }, [loadConsultationData, sessionId]);

  // Consultation elapsed timer
  useEffect(() => {
    if (!consultation || consultation.status === "completed") return;

    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [consultation]);

  const formatElapsed = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleAddPrescription = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRx.trim()) return;
    const updated = [...prescriptions, newRx.trim()];
    setPrescriptions(updated);
    consultationService.addPrescription(newRx.trim());
    setNewRx("");
  };

  const handleRemovePrescription = (index: number) => {
    const updated = prescriptions.filter((_, idx) => idx !== index);
    setPrescriptions(updated);
  };

  // Save draft notes to backend database
  const handleSaveDraft = async () => {
    if (!consultation || isSavingDraft || isCompleting) return;
    setIsSavingDraft(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const updated = await consultationService.saveConsultationNotes(consultation.id, {
        clinicalNotes: notes,
        diagnosis,
        prescriptions,
        followUpRecommendation: followUp,
      });
      setConsultation(updated);
      setSuccessMessage(
        `Clinical record saved at ${new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        })}`
      );
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to persist clinical notes.";
      setErrorMessage(msg);
    } finally {
      setIsSavingDraft(false);
    }
  };

  // Complete consultation atomically
  const handleCompleteConsultation = async () => {
    if (isCompleting || !consultation) return;
    setIsCompleting(true);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await consultationService.completeConsultation(consultation.queueEntryId, {
        clinicalNotes: notes,
        diagnosis,
        prescriptions,
        followUpRecommendation: followUp,
      });
      router.push("/doctor/queue");
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Could not complete consultation on server.");
      }
      setIsCompleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="max-w-xl mx-auto space-y-4 pt-16 text-center">
        <Activity size={32} className="animate-spin text-teal-700 mx-auto" />
        <p className="text-sm font-semibold text-slate-700">
          Loading clinical encounter surface...
        </p>
      </div>
    );
  }

  if (errorMessage && !consultation) {
    return (
      <div className="max-w-xl mx-auto space-y-4 pt-10">
        <div className="p-6 rounded-2xl bg-white border border-rose-200 shadow-xs space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="text-rose-600 shrink-0 mt-0.5" />
            <div>
              <h3 className="text-sm font-bold text-rose-900">
                Consultation Error
              </h3>
              <p className="text-xs text-rose-700 mt-0.5">{errorMessage}</p>
            </div>
          </div>
          <div className="pt-2 flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => router.push("/doctor/queue")}
            >
              Return to Doctor Queue
            </Button>
            <Button
              size="sm"
              onClick={loadConsultationData}
              className="bg-teal-700 hover:bg-teal-800 text-white"
            >
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (!consultation) {
    return (
      <div className="max-w-xl mx-auto space-y-6 pt-10 text-center">
        <div className="p-4 bg-teal-50 text-teal-700 rounded-full w-16 h-16 mx-auto flex items-center justify-center">
          <FileText size={32} />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold text-slate-900">
            No Active Consultation
          </h1>
          <p className="text-sm text-slate-500">
            Select a waiting or called patient from your appointments or live queue to start an active encounter.
          </p>
        </div>
        <div className="flex justify-center gap-3">
          <Button onClick={() => router.push("/doctor/queue")} className="bg-teal-700 hover:bg-teal-800">
            Open Live Queue
          </Button>
          <Button variant="outline" onClick={() => router.push("/doctor/appointments")}>
            View Appointments
          </Button>
        </div>
      </div>
    );
  }

  const isCompleted = consultation.status === "completed";
  const isOverExpectedTime = elapsedSeconds > 18 * 60;
  const patientDisplayName = consultation.patientName || `Patient (${consultation.patientId.slice(0, 8)})`;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Notifications */}
      {errorMessage && (
        <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-center justify-between gap-2 shadow-2xs">
          <div className="flex items-center gap-2">
            <AlertCircle size={16} className="text-rose-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-rose-500 hover:text-rose-700 p-1">
            ✕
          </button>
        </div>
      )}

      {successMessage && (
        <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center justify-between gap-2 shadow-2xs">
          <div className="flex items-center gap-2">
            <CheckCircle size={16} className="text-emerald-600 shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-emerald-500 hover:text-emerald-700 p-1">
            ✕
          </button>
        </div>
      )}

      {/* Completed Record Banner */}
      {isCompleted && (
        <div className="p-4 bg-slate-100 border border-slate-300 rounded-xl text-xs text-slate-700 flex items-center gap-2.5 shadow-2xs">
          <Lock size={16} className="text-slate-500 shrink-0" />
          <div>
            <span className="font-bold block text-slate-900">
              Consultation Finalized & Archived
            </span>
            <span>
              This clinical encounter was completed at {consultation.endTime || "a previous session"}. Clinical notes and diagnosis are preserved in read-only format for medical record integrity.
            </span>
          </div>
        </div>
      )}

      {/* Top Clinical Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900 text-white p-4 rounded-xl shadow-md">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/doctor/queue")}
            className="text-slate-300 hover:text-white hover:bg-slate-800 p-2 h-auto"
          >
            <ArrowLeft size={16} />
          </Button>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-teal-400 block">
              {isCompleted ? "Archived Outpatient Encounter" : "Active Outpatient Work Surface"}
            </span>
            <span className="text-base font-bold">
              Patient: {patientDisplayName}
            </span>
          </div>
        </div>

        {/* Live Consultation Timer & Expected Duration Range */}
        <div className="flex items-center gap-4 bg-slate-800 px-4 py-2 rounded-lg border border-slate-700">
          <div>
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              {isCompleted ? "Total Duration" : "Elapsed Time"}
            </span>
            <span
              className={`text-lg font-bold font-mono ${
                isCompleted
                  ? "text-slate-300"
                  : isOverExpectedTime
                  ? "text-amber-400"
                  : "text-teal-400"
              }`}
            >
              {formatElapsed(elapsedSeconds)}
            </span>
          </div>
          <div className="border-l border-slate-700 pl-3">
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              Est. Duration Range
            </span>
            <span className="text-xs font-semibold text-slate-200">
              {consultation.expectedDurationRange.min}–{consultation.expectedDurationRange.max} min
            </span>
          </div>
        </div>
      </div>

      {/* Patient Triage & Clinical Intake Context (Side-by-side) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Left: Triage & Intake Context */}
        <div className="md:col-span-1 space-y-4">
          <Card className="border-slate-200 bg-white shadow-xs">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center justify-between">
                <span className="flex items-center gap-1.5">
                  <ShieldCheck size={14} className="text-teal-600" />
                  Intake & Triage Summary
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-teal-50 text-teal-700 border border-teal-200">
                  {preConsultationReport?.urgency || consultation.intakeSummary?.urgency || "ROUTINE"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Chief Complaint
                </span>
                <p className="font-semibold text-slate-900 mt-0.5">
                  {preConsultationReport?.chief_complaint || consultation.intakeSummary?.chiefComplaint || "Routine clinical review"}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-2 border-t border-slate-100 pt-2">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                    Duration
                  </span>
                  <p className="font-medium text-slate-800 mt-0.5">
                    {preConsultationReport?.symptom_duration || consultation.intakeSummary?.duration || "Not reported"}
                  </p>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                    Reported Severity
                  </span>
                  <p className="font-medium text-slate-800 mt-0.5">
                    {preConsultationReport?.patient_reported_severity != null
                      ? `${preConsultationReport.patient_reported_severity} / 10`
                      : consultation.intakeSummary?.severity != null
                      ? `${consultation.intakeSummary.severity} / 10`
                      : "Not reported"}
                  </p>
                </div>
              </div>

              <div className="border-t border-slate-100 pt-2">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Triage Specialty Routing
                </span>
                <p className="font-semibold text-teal-800 mt-0.5">
                  {preConsultationReport?.recommended_specialty_name || consultation.intakeSummary?.specialty || "General Medicine"}
                </p>
              </div>

              <div className="border-t border-slate-100 pt-2">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Present Symptoms (Affirmed)
                </span>
                <ul className="mt-1 space-y-1">
                  {(preConsultationReport?.present_symptoms || consultation.intakeSummary?.presentSymptoms || []).length > 0 ? (
                    (preConsultationReport?.present_symptoms || consultation.intakeSummary?.presentSymptoms || []).map((s, idx) => (
                      <li key={idx} className="flex items-start gap-1.5 text-slate-800 font-medium">
                        <span className="text-emerald-600 font-bold">•</span>
                        <span>{s} <span className="text-[9px] font-semibold text-emerald-700 bg-emerald-50 px-1 py-0.2 rounded border border-emerald-200">PRESENT</span></span>
                      </li>
                    ))
                  ) : (
                    <li className="text-slate-400 italic">None specifically affirmed</li>
                  )}
                </ul>
              </div>

              <div className="border-t border-slate-100 pt-2">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Pertinent Negatives (Explicitly Denied)
                </span>
                <ul className="mt-1 space-y-1">
                  {(preConsultationReport?.absent_symptoms || consultation.intakeSummary?.absentSymptoms || []).length > 0 ? (
                    (preConsultationReport?.absent_symptoms || consultation.intakeSummary?.absentSymptoms || []).map((s, idx) => (
                      <li key={idx} className="flex items-start gap-1.5 text-slate-600">
                        <span className="text-slate-400 font-bold">•</span>
                        <span>{s} <span className="text-[9px] font-semibold text-slate-500 bg-slate-100 px-1 py-0.2 rounded">DENIED</span></span>
                      </li>
                    ))
                  ) : (
                    <li className="text-slate-400 italic">None recorded</li>
                  )}
                </ul>
              </div>

              <div className="border-t border-slate-100 pt-2 text-[10px] text-slate-400 leading-tight">
                Pre-consultation intake summary only. Clinical assessment and diagnosis remain the responsibility of the treating physician.
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: Notes, Diagnosis, Prescriptions, Follow-up, Completion */}
        <div className="md:col-span-2 space-y-4">
          {/* Clinical Assessment Notes */}
          <Card className="border-slate-200 bg-white shadow-xs">
            <CardHeader className="pb-2 flex flex-row items-center justify-between">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <FileText size={14} className="text-slate-600" />
                Physician Clinical Notes
              </CardTitle>
              {!isCompleted && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleSaveDraft}
                  isLoading={isSavingDraft}
                  disabled={isSavingDraft || isCompleting}
                  className="h-7 text-[11px] gap-1 text-teal-800 border-teal-300 hover:bg-teal-50"
                >
                  <Save size={12} />
                  Save Notes to Record
                </Button>
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                rows={4}
                value={notes}
                disabled={isCompleted}
                onChange={(e) => {
                  setNotes(e.target.value);
                  consultationService.updateNotes(e.target.value);
                }}
                placeholder="Enter objective findings, auscultation, exam notes, clinical impression..."
                className="w-full text-xs md:text-sm p-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500 font-sans leading-relaxed disabled:bg-slate-50 disabled:text-slate-600"
              />

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                  Working Diagnosis
                </label>
                <input
                  type="text"
                  value={diagnosis}
                  disabled={isCompleted}
                  onChange={(e) => {
                    setDiagnosis(e.target.value);
                    consultationService.updateDiagnosis(e.target.value);
                  }}
                  placeholder="e.g., Essential Hypertension, benign without acute crisis"
                  className="w-full text-xs md:text-sm p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-slate-50 disabled:text-slate-600"
                />
              </div>

              <div className="space-y-1.5 pt-1">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                  Follow-up Instructions & Care Advice
                </label>
                <input
                  type="text"
                  value={followUp}
                  disabled={isCompleted}
                  onChange={(e) => setFollowUp(e.target.value)}
                  placeholder="e.g., Re-check blood pressure in 2 weeks; return if headaches worsen"
                  className="w-full text-xs md:text-sm p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:bg-slate-50 disabled:text-slate-600"
                />
              </div>
            </CardContent>
          </Card>

          {/* Orders & Prescriptions */}
          <Card className="border-slate-200 bg-white shadow-xs">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <Pill size={14} className="text-teal-600" />
                Prescriptions & Orders
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5">
                {prescriptions.map((rx, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-slate-50 rounded-lg border border-slate-200 text-xs font-medium text-slate-800 flex items-center justify-between"
                  >
                    <span>{rx}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        Prescribed
                      </span>
                      {!isCompleted && (
                        <button
                          type="button"
                          onClick={() => handleRemovePrescription(idx)}
                          className="text-slate-400 hover:text-rose-600 p-1"
                          title="Remove item"
                        >
                          <Trash2 size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {prescriptions.length === 0 && (
                  <p className="text-xs text-slate-400 italic">No medications or orders added yet.</p>
                )}
              </div>

              {!isCompleted && (
                <form onSubmit={handleAddPrescription} className="flex gap-2 pt-1">
                  <input
                    type="text"
                    value={newRx}
                    onChange={(e) => setNewRx(e.target.value)}
                    placeholder="Add medication or diagnostic test (e.g. Amlodipine 5mg Daily)..."
                    className="flex-1 text-xs p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500"
                  />
                  <Button type="submit" size="sm" variant="secondary" className="gap-1">
                    <Plus size={14} />
                    Add
                  </Button>
                </form>
              )}
            </CardContent>
          </Card>

          {/* Action CTAs */}
          {!isCompleted ? (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 shadow-xs">
              <div className="text-xs text-slate-500">
                Completing will persist notes to the database, conclude the encounter, and advance the queue.
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleSaveDraft}
                  isLoading={isSavingDraft}
                  disabled={isSavingDraft || isCompleting}
                  className="font-semibold gap-1.5 text-xs text-slate-700"
                >
                  <Save size={14} />
                  Save Draft
                </Button>
                <Button
                  size="sm"
                  onClick={handleCompleteConsultation}
                  isLoading={isCompleting}
                  disabled={isCompleting || isSavingDraft}
                  className="bg-emerald-700 hover:bg-emerald-800 font-semibold gap-2 shadow-sm text-xs text-white"
                >
                  <CheckCircle size={15} />
                  Complete Consultation
                </Button>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex items-center justify-between">
              <span className="text-xs text-slate-500">
                Completed encounter. Return to queue station to see waiting patients.
              </span>
              <Button
                size="sm"
                onClick={() => router.push("/doctor/queue")}
                className="bg-teal-700 hover:bg-teal-800 text-white text-xs font-semibold"
              >
                Return to Live Queue
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DoctorConsultationPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-4xl mx-auto p-8 text-center text-slate-500">
          Loading clinical workspace...
        </div>
      }
    >
      <DoctorConsultationInner />
    </Suspense>
  );
}
