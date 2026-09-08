"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { consultationService } from "@/services/consultation";
import { queueService } from "@/services/queue";
import { Consultation, QueueEntry } from "@/types";
import { QueueToken } from "@/components/common/QueueToken";
import { WaitEstimate } from "@/components/common/WaitEstimate";
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
} from "lucide-react";

export default function DoctorConsultationPage() {
  const router = useRouter();
  const [consultation, setConsultation] = useState<Consultation | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [notes, setNotes] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [newRx, setNewRx] = useState("");
  const [prescriptions, setPrescriptions] = useState<string[]>([]);
  const [isCompleting, setIsCompleting] = useState(false);

  useEffect(() => {
    const active = consultationService.getActiveConsultation("doc_202");
    if (active) {
      setConsultation(active);
      setElapsedSeconds(active.elapsedSeconds || 0);
      setNotes(active.clinicalNotes || "");
      setDiagnosis(active.diagnosis || "");
      setPrescriptions(active.prescriptions || []);
    }

    // Active consultation timer
    const interval = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, []);

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

  const handleCompleteConsultation = () => {
    setIsCompleting(true);
    setTimeout(() => {
      if (consultation) {
        queueService.completeConsultation(consultation.queueEntryId);
      }
      consultationService.completeConsultation();
      setIsCompleting(false);
      router.push("/doctor/dashboard");
    }, 450);
  };

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
            Select a waiting patient from your queue to start a clinical intake.
          </p>
        </div>
        <div>
          <Button onClick={() => router.push("/doctor/queue")}>
            Open Room 204 Queue
          </Button>
        </div>
      </div>
    );
  }

  const isOverExpectedTime = elapsedSeconds > 18 * 60;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Top Clinical Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900 text-white p-4 rounded-xl shadow-md">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push("/doctor/dashboard")}
            className="text-slate-300 hover:text-white hover:bg-slate-800 p-2 h-auto"
          >
            <ArrowLeft size={16} />
          </Button>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-teal-400 block">
              Active Outpatient Work Surface
            </span>
            <span className="text-base font-bold">
              Patient: {consultation.patientName}
            </span>
          </div>
        </div>

        {/* Live Consultation Timer & Expected Duration Range */}
        <div className="flex items-center gap-4 bg-slate-800 px-4 py-2 rounded-lg border border-slate-700">
          <div>
            <span className="text-[10px] text-slate-400 uppercase font-semibold block">
              Elapsed Time
            </span>
            <span
              className={`text-lg font-bold font-mono ${
                isOverExpectedTime ? "text-amber-400" : "text-teal-400"
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

      {/* Patient Triage & Clinical Intake Context (Side-by-side or stacked) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Left: Triage & Intake Context */}
        <div className="md:col-span-1 space-y-4">
          <Card className="border-slate-200 bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <ShieldCheck size={14} className="text-teal-600" />
                Intake & Triage Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-xs">
              <div>
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Chief Complaint
                </span>
                <p className="font-semibold text-slate-900 mt-0.5">
                  Hypertension check & medication review. Reports morning dizziness.
                </p>
              </div>

              <div className="border-t border-slate-100 pt-2">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Documented Vitals
                </span>
                <div className="mt-1 space-y-1 font-mono text-slate-700">
                  <div className="flex justify-between">
                    <span>Blood Pressure:</span>
                    <strong className="text-slate-900">138/86 mmHg</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Heart Rate:</span>
                    <strong className="text-slate-900">74 bpm</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>SpO2:</span>
                    <strong className="text-slate-900">98% Room Air</strong>
                  </div>
                </div>
              </div>

              <div className="border-t border-slate-100 pt-2">
                <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                  Confirmed Allergies
                </span>
                <span className="inline-block mt-1 font-semibold text-rose-700 bg-rose-50 px-2 py-0.5 rounded border border-rose-200">
                  Penicillin
                </span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right: Notes, Diagnosis, Prescriptions, Completion */}
        <div className="md:col-span-2 space-y-4">
          {/* Clinical Assessment Notes */}
          <Card className="border-slate-200 bg-white">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs font-bold uppercase tracking-wider text-slate-600 flex items-center gap-1.5">
                <FileText size={14} className="text-slate-600" />
                Physician Clinical Notes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                rows={4}
                value={notes}
                onChange={(e) => {
                  setNotes(e.target.value);
                  consultationService.updateNotes(e.target.value);
                }}
                placeholder="Enter objective findings, auscultation, clinical impression..."
                className="w-full text-xs md:text-sm p-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500 font-sans leading-relaxed"
              />

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">
                  Working Diagnosis
                </label>
                <input
                  type="text"
                  value={diagnosis}
                  onChange={(e) => {
                    setDiagnosis(e.target.value);
                    consultationService.updateDiagnosis(e.target.value);
                  }}
                  placeholder="e.g., Essential Hypertension, benign without acute crisis"
                  className="w-full text-xs md:text-sm p-2.5 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>
            </CardContent>
          </Card>

          {/* Orders & Prescriptions */}
          <Card className="border-slate-200 bg-white">
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
                    <span className="text-[10px] text-emerald-700 font-semibold bg-emerald-50 px-2 py-0.5 rounded">
                      Order Placed
                    </span>
                  </div>
                ))}
              </div>

              <form onSubmit={handleAddPrescription} className="flex gap-2">
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
            </CardContent>
          </Card>

          {/* Complete Consultation CTA */}
          <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              Completing will update queue status and advance the next waiting patient.
            </div>
            <Button
              size="lg"
              onClick={handleCompleteConsultation}
              isLoading={isCompleting}
              className="bg-emerald-700 hover:bg-emerald-800 font-semibold gap-2 shadow-sm"
            >
              <CheckCircle size={16} />
              Complete Consultation
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
