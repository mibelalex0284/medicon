"use client";

import React, { useState, useEffect, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  triageService,
  TriageApiError,
  TriageAssessmentResponse,
  TriageMessageResponse,
} from "@/services/triage";
import { EmergencyBanner } from "@/components/common/EmergencyBanner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Send,
  Bot,
  User,
  CheckCircle2,
  ArrowRight,
  RotateCcw,
  Stethoscope,
  Sparkles,
  AlertCircle,
  Activity,
  ShieldAlert,
} from "lucide-react";
import { RedFlagAlert } from "@/types";
import { EMERGENCY_CONTACT } from "@/lib/constants";

const TRIAGE_SESSION_ID_KEY = "careroute_triage_session_id";

interface ChatMessage {
  id: string;
  sender: "patient" | "assistant";
  content: string;
  createdAt?: string;
}

function TriageChatContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  const [isRetryableError, setIsRetryableError] = useState(false);
  const [isQuotaExhausted, setIsQuotaExhausted] = useState(false);
  const [safetyAlert, setSafetyAlert] = useState<RedFlagAlert | null>(null);
  const [isCompleted, setIsCompleted] = useState(false);
  const [assessment, setAssessment] = useState<TriageAssessmentResponse | null>(
    null
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Session persistence on initial mount
  useEffect(() => {
    let isMounted = true;

    async function initializeSession() {
      const storedSessionId =
        typeof window !== "undefined"
          ? sessionStorage.getItem(TRIAGE_SESSION_ID_KEY)
          : null;

      if (storedSessionId) {
        try {
          // Restore conversation history from existing session
          const [history, sessionDetails] = await Promise.all([
            triageService.getSessionMessages(storedSessionId),
            triageService.getSession(storedSessionId).catch(() => null),
          ]);

          if (isMounted) {
            setSessionId(storedSessionId);

            if (history && history.length > 0) {
              setMessages(
                history.map((m: TriageMessageResponse) => ({
                  id: m.id,
                  sender: m.sender === "assistant" ? "assistant" : "patient",
                  content: m.content,
                  createdAt: m.created_at,
                }))
              );
            }

            if (sessionDetails?.assessment) {
              setAssessment(sessionDetails.assessment);
              if (sessionDetails.assessment.red_flag_detected) {
                setSafetyAlert({
                  isTriggered: true,
                  title: "Critical Warning Signs Detected",
                  message:
                    sessionDetails.assessment.guidance ||
                    "Emergency warning signs were identified. Emergency evaluation is required.",
                  actionRecommendation:
                    sessionDetails.assessment.guidance ||
                    EMERGENCY_CONTACT.guidanceText,
                  hotline: EMERGENCY_CONTACT.hotlineText,
                });
              } else if (
                sessionDetails.status === "COMPLETED" ||
                sessionDetails.status === "ESCALATED"
              ) {
                setIsCompleted(true);
              }
            }
          }
        } catch {
          // If session is expired or invalid in backend, clean up gracefully
          if (typeof window !== "undefined") {
            sessionStorage.removeItem(TRIAGE_SESSION_ID_KEY);
          }
          if (isMounted) {
            setSessionId(null);
          }
        }
      }

      // If no stored session or clean start, check URL/session concern to prefill input
      if (!storedSessionId && isMounted) {
        const urlConcern = searchParams.get("concern");
        const storedConcern =
          typeof window !== "undefined"
            ? sessionStorage.getItem("careroute_patient_concern")
            : null;
        const initialText = urlConcern || storedConcern || "";
        if (initialText) {
          setInputText(initialText);
        }
      }

      if (isMounted) {
        setIsInitializing(false);
      }
    }

    initializeSession();

    return () => {
      isMounted = false;
    };
  }, [searchParams]);

  const handleSendMessage = async (e?: React.FormEvent, retryText?: string) => {
    if (e) e.preventDefault();

    const isRetry = typeof retryText === "string";
    const textToSend = (isRetry ? retryText : inputText).trim();
    if (!textToSend || isLoading || safetyAlert || isCompleted) return;

    setErrorMessage(null);
    setIsRetryableError(false);

    // Retain the message text for recovery before clearing input
    setFailedMessage(textToSend);
    if (!isRetry) {
      setInputText("");
    }

    // Append patient message to chat only if not already displayed
    setMessages((prev) => {
      const lastMsg = prev[prev.length - 1];
      if (lastMsg && lastMsg.sender === "patient" && lastMsg.content === textToSend) {
        return prev;
      }
      const patientMsgId = `patient-${Date.now()}`;
      return [
        ...prev,
        {
          id: patientMsgId,
          sender: "patient",
          content: textToSend,
          createdAt: new Date().toISOString(),
        },
      ];
    });

    setIsLoading(true);

    try {
      let currentSessionId = sessionId;

      // 1. If first turn, create session with original_input
      if (!currentSessionId) {
        const newSession = await triageService.createSession({
          original_input: textToSend,
          language: "en",
        });
        currentSessionId = newSession.id;
        setSessionId(currentSessionId);
        if (typeof window !== "undefined") {
          sessionStorage.setItem(TRIAGE_SESSION_ID_KEY, currentSessionId);
          sessionStorage.setItem("careroute_patient_concern", textToSend);
        }
      }

      // 2. Process message through conversational triage endpoint
      const turn = await triageService.sendMessage(currentSessionId, textToSend);

      // On successful turn, clear failedMessage since it was successfully processed
      setFailedMessage(null);

      // 3. Render assistant response
      const assistantMsgId = `assistant-${Date.now()}`;
      setMessages((prev) => [
        ...prev,
        {
          id: assistantMsgId,
          sender: "assistant",
          content: turn.assistant_message,
          createdAt: new Date().toISOString(),
        },
      ]);

      // 4. Handle safety flags and emergency red flags
      const isRedFlag =
        (turn.safety_flags && turn.safety_flags.length > 0) ||
        turn.stop_reason === "EMERGENCY_RED_FLAG";

      if (isRedFlag) {
        const alert: RedFlagAlert = {
          isTriggered: true,
          title: "Critical Warning Signs Detected",
          message:
            turn.assistant_message ||
            turn.assessment?.guidance ||
            "Emergency warning signs were detected during clinical triage intake.",
          actionRecommendation:
            turn.assessment?.guidance ||
            EMERGENCY_CONTACT.guidanceText,
          hotline: EMERGENCY_CONTACT.hotlineText,
        };
        setSafetyAlert(alert);
        if (turn.assessment) {
          setAssessment(turn.assessment);
        }
        return;
      }

      // 5. Handle completion
      if (turn.is_complete) {
        setIsCompleted(true);
        if (turn.assessment) {
          setAssessment(turn.assessment);
          if (typeof window !== "undefined") {
            const specialtyName =
              turn.assessment.recommended_specialty_name || "General Medicine";
            sessionStorage.setItem(
              "careroute_triage_specialties",
              JSON.stringify([specialtyName])
            );
            if (turn.assessment.recommended_specialty_id) {
              sessionStorage.setItem(
                "careroute_triage_specialty_id",
                turn.assessment.recommended_specialty_id
              );
            }
            sessionStorage.setItem(
              "careroute_triage_care_direction",
              turn.assessment.guidance || "Outpatient Clinical Consultation"
            );
          }
        }
      }
    } catch (err: unknown) {
      let message = "An unexpected error occurred during triage processing.";
      let isTransient = false;
      let isCapacityExhausted = false;

      if (err instanceof TriageApiError) {
        message = err.message;
        const msgLower = message.toLowerCase();
        isCapacityExhausted =
          msgLower.includes("capacity is temporarily exhausted") ||
          msgLower.includes("quota") ||
          msgLower.includes("rate limit") ||
          err.code === "TRIAGE_LLM_QUOTA_EXHAUSTED";

        if (
          !isCapacityExhausted &&
          (err.status === 503 ||
            err.status === 502 ||
            err.status === 504 ||
            err.status === 500 ||
            err.code === "TRIAGE_LLM_SERVICE_UNAVAILABLE" ||
            msgLower.includes("temporarily unavailable"))
        ) {
          isTransient = true;
        }
      } else if (err instanceof Error) {
        message = err.message;
        const msgLower = message.toLowerCase();
        isCapacityExhausted =
          msgLower.includes("capacity is temporarily exhausted") ||
          msgLower.includes("quota") ||
          msgLower.includes("rate limit");

        if (
          !isCapacityExhausted &&
          (msgLower.includes("temporarily unavailable") ||
            msgLower.includes("failed to fetch") ||
            msgLower.includes("network") ||
            msgLower.includes("timeout") ||
            msgLower.includes("503"))
        ) {
          isTransient = true;
        }
      }

      setErrorMessage(message);
      setIsRetryableError(isTransient && !isCapacityExhausted);
      setIsQuotaExhausted(isCapacityExhausted);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const handleResetSession = () => {
    if (typeof window !== "undefined") {
      sessionStorage.removeItem(TRIAGE_SESSION_ID_KEY);
      sessionStorage.removeItem("careroute_triage_specialties");
      sessionStorage.removeItem("careroute_triage_specialty_id");
      sessionStorage.removeItem("careroute_triage_care_direction");
    }
    setSessionId(null);
    setMessages([]);
    setInputText("");
    setErrorMessage(null);
    setFailedMessage(null);
    setIsRetryableError(false);
    setIsQuotaExhausted(false);
    setSafetyAlert(null);
    setIsCompleted(false);
    setAssessment(null);
  };

  const handleProceedToDoctorMatching = () => {
    const storedHospId =
      typeof window !== "undefined"
        ? sessionStorage.getItem("careroute_selected_hospital_id")
        : null;
    const params = new URLSearchParams();
    if (sessionId) {
      params.set("session_id", sessionId);
    }
    if (storedHospId) {
      params.set("hospital_id", storedHospId);
    }
    const query = params.toString();
    router.push(query ? `/patient/doctors?${query}` : "/patient/doctors");
  };

  const isInputDisabled =
    isLoading || isInitializing || Boolean(safetyAlert) || isCompleted;

  if (isInitializing) {
    return (
      <div className="max-w-3xl mx-auto p-12 text-center space-y-4">
        <div className="inline-flex items-center justify-center p-3 rounded-full bg-sky-50 text-sky-600 animate-spin">
          <Activity size={24} />
        </div>
        <p className="text-sm font-medium text-slate-600">
          Connecting to MediLink clinical triage service...
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header with status badge & controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200/80 pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-100 text-sky-800">
              <Stethoscope size={13} />
              Conversational Intake
            </span>
            {isCompleted && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-800">
                <CheckCircle2 size={13} />
                Assessment Complete
              </span>
            )}
            {safetyAlert && (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-100 text-red-800">
                <ShieldAlert size={13} />
                Safety Stop
              </span>
            )}
          </div>
          <h1 className="text-xl md:text-2xl font-bold text-slate-900 tracking-tight">
            Adaptive Clinical Triage
          </h1>
          <p className="text-xs md:text-sm text-slate-500">
            Conversational symptom navigation guided by backend clinical reasoning.
          </p>
        </div>

        {sessionId && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleResetSession}
            className="text-xs text-slate-600 self-start sm:self-auto gap-1.5"
            title="Start a fresh triage conversation"
          >
            <RotateCcw size={14} />
            Start New Session
          </Button>
        )}
      </div>

      {/* Emergency Red Flag Banner */}
      {safetyAlert && <EmergencyBanner alert={safetyAlert} />}

      {/* Completion Assessment Card */}
      {isCompleted && assessment && (
        <Card className="border-emerald-200 bg-emerald-50/40 shadow-sm animate-in fade-in duration-300">
          <CardHeader className="pb-3 border-b border-emerald-100">
            <div className="flex items-center justify-between">
              <CardTitle className="text-emerald-950 flex items-center gap-2 text-base md:text-lg">
                <CheckCircle2 className="text-emerald-600" size={20} />
                Clinical Intake Assessment Summary
              </CardTitle>
              <span
                className={`text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded border ${
                  assessment.urgency === "HIGH"
                    ? "bg-amber-100 text-amber-900 border-amber-300"
                    : assessment.urgency === "MODERATE"
                    ? "bg-sky-100 text-sky-900 border-sky-300"
                    : "bg-emerald-100 text-emerald-800 border-emerald-300"
                }`}
              >
                Urgency: {assessment.urgency}
              </span>
            </div>
          </CardHeader>
          <CardContent className="pt-4 space-y-4 text-sm text-slate-800">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block mb-1">
                Recommended Clinical Specialty
              </span>
              <span className="inline-block font-bold text-sky-900 text-base bg-white border border-sky-200 px-3 py-1 rounded-lg shadow-2xs">
                {assessment.recommended_specialty_name || "General Medicine"}
              </span>
            </div>

            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block mb-1">
                Clinical Guidance
              </span>
              <p className="leading-relaxed bg-white p-3.5 rounded-lg border border-slate-200 text-slate-700">
                {assessment.guidance}
              </p>
            </div>

            {assessment.rationale && (
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500 block mb-1">
                  Clinical Rationale
                </span>
                <p className="text-xs text-slate-600 leading-normal bg-white/70 p-3 rounded-lg border border-slate-200/80">
                  {assessment.rationale}
                </p>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <Button
                onClick={handleProceedToDoctorMatching}
                size="md"
                className="gap-2 font-semibold shadow-sm"
              >
                Continue to Doctor Matching
                <ArrowRight size={16} />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Graceful API Error Alert */}
      {errorMessage && (
        <div
          role="alert"
          className="rounded-xl border border-rose-300 bg-rose-50 p-4 text-rose-950 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-xs animate-in fade-in duration-150"
        >
          <div className="flex items-start gap-3 flex-1">
            <AlertCircle size={20} className="text-rose-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <h4 className="font-semibold text-sm text-rose-900">
                {isQuotaExhausted
                  ? "Triage Capacity Limit Reached"
                  : isRetryableError
                  ? "Service Temporarily Unavailable"
                  : errorMessage.includes("temporarily unavailable")
                  ? "Service Temporarily Unavailable"
                  : "Communication Error"}
              </h4>
              <p className="text-xs md:text-sm text-rose-800">{errorMessage}</p>
              {isQuotaExhausted ? (
                <p className="text-xs text-rose-700 font-medium">
                  Your intake history has been saved. Due to temporary AI capacity limits, repeated attempts right now are unlikely to succeed. You can proceed directly to choose a doctor or check back later.
                </p>
              ) : (
                isRetryableError && failedMessage && (
                  <p className="text-xs text-rose-700 font-medium">
                    Your message has been preserved. You can retry safely without losing your session.
                  </p>
                )
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-center">
            {isQuotaExhausted ? (
              <Button
                variant="default"
                size="sm"
                onClick={handleProceedToDoctorMatching}
                className="text-xs bg-sky-700 hover:bg-sky-800 text-white shadow-2xs flex items-center gap-1.5"
              >
                Find Available Doctors
                <ArrowRight size={13} />
              </Button>
            ) : (
              isRetryableError && failedMessage && (
                <Button
                  variant="default"
                  size="sm"
                  disabled={isLoading}
                  onClick={() => handleSendMessage(undefined, failedMessage)}
                  className="text-xs bg-rose-600 hover:bg-rose-700 text-white shadow-2xs flex items-center gap-1.5"
                >
                  <RotateCcw size={13} className={isLoading ? "animate-spin" : ""} />
                  Retry
                </Button>
              )
            )}
            <Button
              variant="outline"
              size="sm"
              disabled={isLoading}
              onClick={() => {
                setErrorMessage(null);
                setIsRetryableError(false);
                setIsQuotaExhausted(false);
              }}
              className="text-xs border-rose-200 bg-white hover:bg-rose-100 text-rose-900"
            >
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {/* Chronological Chat Container */}
      <Card className="border-slate-200 shadow-sm overflow-hidden flex flex-col bg-slate-50/50">
        <div className="p-4 md:p-6 space-y-4 min-h-[340px] max-h-[520px] overflow-y-auto">
          {/* Default initial message if history is empty */}
          {messages.length === 0 && (
            <div className="flex items-start gap-3 animate-in fade-in duration-200">
              <div className="w-8 h-8 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center shrink-0 mt-0.5 border border-sky-200 shadow-2xs">
                <Bot size={16} />
              </div>
              <div className="space-y-1 max-w-[85%]">
                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                  Clinical Intake Assistant
                </span>
                <div className="bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-xs p-4 shadow-2xs text-sm leading-relaxed">
                  Hello! I am your MediLink clinical intake assistant. Please
                  describe your symptoms, how long you have had them, and any
                  specific discomfort you are experiencing today.
                </div>
              </div>
            </div>
          )}

          {/* Chronological Message List */}
          {messages.map((message) => {
            const isPatient = message.sender === "patient";

            return (
              <div
                key={message.id}
                className={`flex items-start gap-3 animate-in fade-in duration-150 ${
                  isPatient ? "flex-row-reverse" : "flex-row"
                }`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5 border shadow-2xs ${
                    isPatient
                      ? "bg-slate-800 text-white border-slate-700"
                      : "bg-sky-100 text-sky-700 border-sky-200"
                  }`}
                >
                  {isPatient ? <User size={16} /> : <Bot size={16} />}
                </div>

                <div
                  className={`space-y-1 max-w-[85%] sm:max-w-[78%] ${
                    isPatient ? "text-right" : "text-left"
                  }`}
                >
                  <span className="text-[11px] font-medium text-slate-400 block px-1">
                    {isPatient ? "You" : "Clinical Assistant"}
                  </span>
                  <div
                    className={`p-3.5 md:p-4 text-sm leading-relaxed whitespace-pre-wrap ${
                      isPatient
                        ? "bg-sky-600 text-white rounded-2xl rounded-tr-xs shadow-xs"
                        : "bg-white border border-slate-200/90 text-slate-800 rounded-2xl rounded-tl-xs shadow-xs"
                    }`}
                  >
                    {message.content}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Loading / Typing State */}
          {isLoading && (
            <div className="flex items-start gap-3 animate-in fade-in duration-150">
              <div className="w-8 h-8 rounded-full bg-sky-100 text-sky-700 flex items-center justify-center shrink-0 mt-0.5 border border-sky-200">
                <Bot size={16} />
              </div>
              <div className="space-y-1">
                <span className="text-[11px] font-medium text-slate-400 block px-1">
                  Clinical Assistant
                </span>
                <div className="bg-white border border-slate-200 rounded-2xl rounded-tl-xs px-4 py-3 shadow-2xs flex items-center gap-2 text-xs text-slate-500">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-sky-600 animate-pulse" />
                    <span
                      className="w-2 h-2 rounded-full bg-sky-600 animate-pulse"
                      style={{ animationDelay: "150ms" }}
                    />
                    <span
                      className="w-2 h-2 rounded-full bg-sky-600 animate-pulse"
                      style={{ animationDelay: "300ms" }}
                    />
                  </div>
                  <span className="font-medium text-slate-600">
                    Evaluating clinical presentation...
                  </span>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Bar */}
        <div className="p-3 md:p-4 bg-white border-t border-slate-200/80">
          <form
            onSubmit={handleSendMessage}
            className="flex items-end gap-2.5"
          >
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                rows={2}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={isInputDisabled}
                placeholder={
                  safetyAlert
                    ? "Triage stopped due to critical safety alert. Follow emergency guidelines above."
                    : isCompleted
                    ? "Triage completed. Proceed to doctor matching above."
                    : "Describe your symptoms or answer the assistant's question..."
                }
                className="w-full resize-none rounded-xl border border-slate-300 p-3 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-transparent disabled:bg-slate-100 disabled:text-slate-400 transition-colors"
              />
            </div>

            <Button
              type="submit"
              disabled={isInputDisabled || !inputText.trim()}
              isLoading={isLoading}
              size="md"
              className="h-11 px-4 rounded-xl gap-2 font-semibold shrink-0"
              title="Send message"
            >
              <span>Send</span>
              <Send size={15} />
            </Button>
          </form>

          <p className="text-[11px] text-slate-400 mt-2 px-1 flex items-center justify-between">
            <span>
              Press <kbd className="px-1 py-0.5 bg-slate-100 border border-slate-200 rounded text-[10px]">Enter</kbd> to send, <kbd className="px-1 py-0.5 bg-slate-100 border border-slate-200 rounded text-[10px]">Shift + Enter</kbd> for new line
            </span>
            <span className="hidden sm:inline-flex items-center gap-1 text-slate-400">
              <Sparkles size={11} />
              MediLink Triage Engine
            </span>
          </p>
        </div>
      </Card>
    </div>
  );
}

export default function TriagePage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-3xl mx-auto p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-slate-100 text-slate-400 animate-spin">
            <Activity size={20} />
          </div>
          <p className="text-sm text-slate-500">Loading clinical triage...</p>
        </div>
      }
    >
      <TriageChatContent />
    </Suspense>
  );
}
