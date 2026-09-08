"use client";

import React, { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  CLINICAL_TRIAGE_QUESTIONS,
  triageService,
} from "@/services/triage";
import { EmergencyBanner } from "@/components/common/EmergencyBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Stethoscope,
  ClipboardList,
} from "lucide-react";
import { RedFlagAlert } from "@/types";

function TriageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [chiefComplaint, setChiefComplaint] = useState("");
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [activeRedFlag, setActiveRedFlag] = useState<RedFlagAlert | undefined>(undefined);
  const [isCompleted, setIsCompleted] = useState(false);
  const [confirmedFacts, setConfirmedFacts] = useState<string[]>([]);
  const [recommendedSpecialties, setRecommendedSpecialties] = useState<string[]>([]);
  const [careDirection, setCareDirection] = useState("");

  useEffect(() => {
    const urlConcern = searchParams.get("concern");
    const storedConcern =
      typeof window !== "undefined"
        ? sessionStorage.getItem("careroute_patient_concern")
        : null;
    const initialConcern =
      urlConcern || storedConcern || "Persistent dry cough for 4 days";
    setChiefComplaint(initialConcern);
  }, [searchParams]);

  const currentQuestion = CLINICAL_TRIAGE_QUESTIONS[currentStepIndex];
  const totalQuestions = CLINICAL_TRIAGE_QUESTIONS.length;
  const progressPercent = Math.round(((currentStepIndex + 1) / totalQuestions) * 100);

  const handleSelectOption = (optionId: string, isMulti?: boolean) => {
    const qId = currentQuestion.id;
    if (isMulti) {
      const existing = answers[qId] || [];
      if (optionId === "none_of_above") {
        setAnswers({ ...answers, [qId]: ["none_of_above"] });
      } else {
        const filtered = existing.filter((item) => item !== "none_of_above");
        if (filtered.includes(optionId)) {
          setAnswers({
            ...answers,
            [qId]: filtered.filter((i) => i !== optionId),
          });
        } else {
          setAnswers({ ...answers, [qId]: [...filtered, optionId] });
        }
      }
    } else {
      setAnswers({ ...answers, [qId]: [optionId] });
    }
  };

  const handleNext = () => {
    // Evaluate for red flags on the fly
    const evaluation = triageService.evaluateTriageAnswers(chiefComplaint, answers);

    if (evaluation.redFlagAlert?.isTriggered) {
      setActiveRedFlag(evaluation.redFlagAlert);
      return;
    }

    if (currentStepIndex < totalQuestions - 1) {
      setCurrentStepIndex((prev) => prev + 1);
    } else {
      // Completed all steps -> finalize evaluation
      setConfirmedFacts(evaluation.confirmedFacts);
      setRecommendedSpecialties(evaluation.recommendedSpecialties);
      setCareDirection(evaluation.careDirection);
      setIsCompleted(true);

      // Save to session for Doctor Matching
      if (typeof window !== "undefined") {
        sessionStorage.setItem(
          "careroute_triage_specialties",
          JSON.stringify(evaluation.recommendedSpecialties)
        );
        sessionStorage.setItem(
          "careroute_triage_care_direction",
          evaluation.careDirection
        );
      }
    }
  };

  const handleBack = () => {
    if (isCompleted) {
      setIsCompleted(false);
    } else if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    } else {
      router.push("/patient/find-care");
    }
  };

  const handleProceedToDoctorMatching = () => {
    router.push("/patient/doctors");
  };

  const currentSelection = answers[currentQuestion?.id] || [];
  const canContinue = currentSelection.length > 0;

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* SEPARATE RED FLAG SEMANTIC LAYER (Shown prominently if triggered) */}
      {activeRedFlag && <EmergencyBanner alert={activeRedFlag} />}

      {/* COMPLETED REVIEW SCREEN (Confirm Important Facts) */}
      {isCompleted ? (
        <div className="space-y-6 animate-in fade-in duration-200">
          <div className="space-y-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-100 text-emerald-800 text-xs font-semibold">
              <CheckCircle2 size={14} />
              Intake Completed
            </span>
            <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
              Confirmation of Important Facts
            </h1>
            <p className="text-sm text-slate-600">
              Please review the key information captured during your intake before we match
              you with a physician.
            </p>
          </div>

          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-5 md:p-6 space-y-4">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Assigned Care Direction
                </span>
                <p className="text-base font-bold text-sky-900 mt-1">
                  {careDirection}
                </p>
              </div>

              <div className="border-t border-slate-100 pt-3">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block mb-2">
                  Clinical Intake Summary:
                </span>
                <ul className="space-y-2 text-sm text-slate-700">
                  {confirmedFacts.map((fact, idx) => (
                    <li key={idx} className="flex items-start gap-2.5">
                      <CheckCircle2
                        size={16}
                        className="text-emerald-600 shrink-0 mt-0.5"
                      />
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="border-t border-slate-100 pt-3 flex items-center justify-between">
                <div>
                  <span className="text-xs text-slate-500 block font-medium">
                    Recommended Specialties
                  </span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {recommendedSpecialties.map((spec) => (
                      <span
                        key={spec}
                        className="text-xs font-semibold bg-sky-100 text-sky-800 px-2.5 py-0.5 rounded-full"
                      >
                        {spec}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2">
            <Button
              variant="outline"
              onClick={() => setIsCompleted(false)}
              className="w-full sm:w-auto"
            >
              <ArrowLeft size={16} className="mr-1.5" />
              Adjust Answers
            </Button>
            <Button
              onClick={handleProceedToDoctorMatching}
              size="lg"
              className="w-full sm:w-auto font-semibold gap-2 shadow-sm"
            >
              View Recommended Doctors
              <ArrowRight size={16} />
            </Button>
          </div>
        </div>
      ) : (
        /* STRUCTURED CLINICAL QUESTIONNAIRE */
        <div className="space-y-6">
          {/* Progress Header */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs text-slate-500 font-semibold">
              <span className="flex items-center gap-1.5 text-sky-700">
                <ClipboardList size={14} />
                Clinical Intake Assessment
              </span>
              <span>
                Question {currentStepIndex + 1} of {totalQuestions}
              </span>
            </div>
            {/* Accessible Progress Bar */}
            <div
              className="w-full bg-slate-200 h-2 rounded-full overflow-hidden"
              role="progressbar"
              aria-valuenow={progressPercent}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="bg-sky-600 h-full transition-all duration-300 rounded-full"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Question Title & Explanation */}
          <div className="space-y-1.5">
            <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight leading-snug">
              {currentQuestion.title}
            </h1>
            {currentQuestion.explanation && (
              <p className="text-xs md:text-sm text-slate-500 leading-relaxed">
                {currentQuestion.explanation}
              </p>
            )}
          </div>

          {/* Structured Options */}
          <div className="space-y-2.5">
            {currentQuestion.options.map((opt) => {
              const isSelected = currentSelection.includes(opt.id);
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() =>
                    handleSelectOption(opt.id, currentQuestion.multiSelect)
                  }
                  className={`w-full text-left p-4 rounded-xl border-2 transition-all flex items-start justify-between gap-3 ${
                    isSelected
                      ? "border-sky-600 bg-sky-50/70 text-slate-900 shadow-2xs"
                      : "border-slate-200 bg-white hover:border-slate-300 text-slate-800"
                  }`}
                >
                  <div className="space-y-0.5">
                    <span className="text-sm font-semibold block leading-tight">
                      {opt.label}
                    </span>
                    {opt.description && (
                      <span className="text-xs text-slate-500 block leading-normal">
                        {opt.description}
                      </span>
                    )}
                  </div>
                  <div
                    className={`h-5 w-5 rounded-${
                      currentQuestion.multiSelect ? "md" : "full"
                    } border flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                      isSelected
                        ? "bg-sky-600 border-sky-600 text-white"
                        : "border-slate-300 bg-white"
                    }`}
                  >
                    {isSelected && <CheckCircle2 size={13} className="stroke-[3]" />}
                  </div>
                </button>
              );
            })}
          </div>

          {/* Navigation Controls */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-200">
            <Button
              variant="outline"
              onClick={handleBack}
              className="gap-1 text-slate-600"
            >
              <ArrowLeft size={16} />
              Back
            </Button>

            <Button
              onClick={handleNext}
              disabled={!canContinue}
              className="gap-1.5 font-semibold"
            >
              {currentStepIndex === totalQuestions - 1
                ? "Review Intake Facts"
                : "Continue"}
              <ArrowRight size={16} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function TriagePage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-sm text-slate-500">Loading clinical triage...</div>}>
      <TriageContent />
    </Suspense>
  );
}
