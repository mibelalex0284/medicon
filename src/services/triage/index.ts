import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { TriageUrgency, RedFlagAlert } from "@/types";

export interface TriageSessionCreate {
  original_input: string;
  language?: string;
}

export interface TriageSessionResponse {
  id: string;
  patient_id: string;
  status: "IN_PROGRESS" | "COMPLETED" | "ESCALATED" | "ABANDONED" | string;
  original_input: string;
  confirmed_input?: string | null;
  language: string;
  started_at: string;
  completed_at?: string | null;
  assessment?: TriageAssessmentResponse | null;
}

export interface TriageMessageCreate {
  content: string;
}

export interface TriageMessageResponse {
  id: string;
  session_id: string;
  sender: "patient" | "assistant" | string;
  content: string;
  turn_index: number;
  created_at: string;
}

export interface SelectedQuestionSummary {
  evidence_id: string;
  question_text: string;
  data_type?: string;
  possible_values?: string[];
  category?: string;
  is_antecedent?: boolean;
  expected_information_gain?: number;
}

export interface TriageAssessmentResponse {
  id: string;
  triage_session_id: string;
  urgency: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  confidence: number;
  needs_escalation: boolean;
  red_flag_detected: boolean;
  red_flag_codes: string[];
  recommended_specialty_id?: string | null;
  recommended_specialty_name?: string | null;
  rationale: string;
  guidance: string;
  assessed_at: string;
}

export interface PreConsultationReportResponse {
  session_id: string;
  patient_id: string;
  assessed_at?: string | null;
  urgency: string;
  recommended_specialty_id?: string | null;
  recommended_specialty_name?: string | null;
  chief_complaint: string;
  symptom_duration?: string | null;
  patient_reported_severity?: number | null;
  present_symptoms: string[];
  absent_symptoms: string[];
  unknown_symptoms: string[];
  safety_screenings: Record<string, string>;
  conversation_summary: string;
  notice: string;
  formatted_report: string;
}

export interface TriageConversationalTurnResponse {
  session_id: string;
  conversation_turn: number;
  is_complete: boolean;
  stop_reason?: string | null;
  patient_message: string;
  assistant_message: string;
  extracted_evidences?: Record<string, unknown>[];
  selected_question?: SelectedQuestionSummary | null;
  completeness_score?: number;
  uncertainty_score: number;
  safety_flags: string[];
  assessment?: TriageAssessmentResponse | null;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (typeof window !== "undefined") {
    // 1. Prioritize live Supabase session for guaranteed active, non-expired token
    try {
      const supabase = getSupabaseClient();
      if (supabase && isSupabaseConfigured()) {
        const { data } = await supabase.auth.getSession();
        if (data?.session?.access_token) {
          localStorage.setItem("careroute_auth_token", data.session.access_token);
          headers["Authorization"] = `Bearer ${data.session.access_token}`;
          return headers;
        }
      }
    } catch {
      // Supabase not configured or in fallback mode
    }

    // 2. Explicit token in localStorage / sessionStorage fallback
    const storedToken =
      localStorage.getItem("careroute_auth_token") ||
      sessionStorage.getItem("careroute_auth_token");
    if (storedToken) {
      headers["Authorization"] = `Bearer ${storedToken}`;
      return headers;
    }
  }

  return headers;
}

export class TriageApiError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "TriageApiError";
    this.status = status;
    this.code = code;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMessage = `HTTP error ${res.status}`;
    let errorCode: string | undefined = undefined;
    try {
      const data = await res.json();
      if (data?.error?.message) {
        errorMessage = data.error.message;
        errorCode = data.error.code;
      } else if (data?.detail) {
        errorMessage =
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail);
      }
    } catch {
      // Response was not JSON
    }
    throw new TriageApiError(errorMessage, res.status, errorCode);
  }
  return res.json() as Promise<T>;
}

export class TriageService {
  /**
   * POST /api/v1/triage/sessions
   * Creates a new triage session with the patient's initial concern.
   */
  async createSession(
    data: TriageSessionCreate
  ): Promise<TriageSessionResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/triage/sessions`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        original_input: data.original_input,
        language: data.language || "en",
      }),
    });
    return handleResponse<TriageSessionResponse>(res);
  }

  /**
   * POST /api/v1/triage/sessions/{session_id}/messages
   * Submits a patient message and returns the next conversational turn.
   */
  async sendMessage(
    sessionId: string,
    content: string
  ): Promise<TriageConversationalTurnResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/triage/sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: "POST",
        headers,
        body: JSON.stringify({ content }),
      }
    );
    return handleResponse<TriageConversationalTurnResponse>(res);
  }

  /**
   * GET /api/v1/triage/sessions/{session_id}/messages
   * Retrieves the chronological message history for a conversational triage session.
   */
  async getSessionMessages(
    sessionId: string
  ): Promise<TriageMessageResponse[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/triage/sessions/${encodeURIComponent(sessionId)}/messages`,
      {
        method: "GET",
        headers,
      }
    );
    return handleResponse<TriageMessageResponse[]>(res);
  }

  /**
   * GET /api/v1/triage/sessions/{session_id}
   * Retrieves details and current status/assessment of a triage session.
   */
  async getSession(sessionId: string): Promise<TriageSessionResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/triage/sessions/${encodeURIComponent(sessionId)}`,
      {
        method: "GET",
        headers,
      }
    );
    return handleResponse<TriageSessionResponse>(res);
  }

  /**
   * GET /api/v1/triage/sessions/{session_id}/report
   * Retrieves the structured Pre-Consultation Intake Report for physician review.
   */
  async getPreConsultationReport(
    sessionId: string
  ): Promise<PreConsultationReportResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/triage/sessions/${encodeURIComponent(sessionId)}/report`,
      {
        method: "GET",
        headers,
      }
    );
    return handleResponse<PreConsultationReportResponse>(res);
  }

  // Deprecated client-side fallback evaluation method preserved for compatibility
  evaluateTriageAnswers(
    chiefComplaint: string,
    answers: Record<string, string[]>
  ): {
    urgency: TriageUrgency;
    redFlagAlert?: RedFlagAlert;
    careDirection: string;
    recommendedSpecialties: string[];
    confirmedFacts: string[];
  } {
    return {
      urgency: "routine",
      careDirection: "Standard Outpatient Consultation & Doctor Matching",
      recommendedSpecialties: ["Internal Medicine"],
      confirmedFacts: [
        `Chief concern: "${chiefComplaint || "Outpatient concern"}"`,
      ],
    };
  }
}

export const triageService = new TriageService();
