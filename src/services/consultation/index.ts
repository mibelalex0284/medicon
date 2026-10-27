import { Consultation } from "@/types";
import { getAuthHeaders } from "@/services/doctors";
import {
  BackendConsultationResponse,
  mapBackendConsultationToFrontend,
  QueueApiError,
} from "@/services/queue";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

let ACTIVE_LOCAL_NOTES: {
  notes: string;
  diagnosis: string;
  prescriptions: string[];
  followUp: string;
} = {
  notes: "",
  diagnosis: "",
  prescriptions: [],
  followUp: "",
};

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMessage = `HTTP error ${res.status}`;
    let errorCode: string | undefined = undefined;
    let detail: unknown = undefined;

    try {
      const data = await res.json();
      if (data?.error?.message) {
        errorMessage = data.error.message;
        errorCode = data.error.code;
      } else if (data?.detail) {
        detail = data.detail;
        if (typeof data.detail === "string") {
          errorMessage = data.detail;
        } else if (Array.isArray(data.detail) && data.detail[0]?.msg) {
          errorMessage = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
          errorCode = "VALIDATION_ERROR";
        } else {
          errorMessage = JSON.stringify(data.detail);
        }
      }
    } catch {
      // Non-JSON response
    }

    throw new QueueApiError(errorMessage, res.status, errorCode, detail);
  }
  return res.json() as Promise<T>;
}

export class ConsultationService {
  /**
   * GET /api/v1/queues/active-consultation
   * Retrieves the doctor's currently active consultation from backend.
   */
  async getActiveConsultation(_doctorId?: string): Promise<Consultation | null> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/queues/active-consultation`, {
      method: "GET",
      headers,
    });

    if (res.status === 404) {
      return null;
    }

    const data = await handleResponse<BackendConsultationResponse | null>(res);
    if (!data) return null;

    const mapped = mapBackendConsultationToFrontend(data);
    // Sync local notes cache with authoritative backend notes
    ACTIVE_LOCAL_NOTES = {
      notes: mapped.clinicalNotes || "",
      diagnosis: mapped.diagnosis || "",
      prescriptions: [...mapped.prescriptions],
      followUp: mapped.followUpRecommendation || "",
    };
    return mapped;
  }

  /**
   * GET /api/v1/queues/consultation/{queue_entry_id}
   * Retrieves consultation associated with a specific queue entry.
   */
  async getConsultationByQueueEntry(queueEntryId: string): Promise<Consultation | null> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/consultation/${encodeURIComponent(queueEntryId)}`,
      {
        method: "GET",
        headers,
      }
    );

    if (res.status === 404) {
      return null;
    }

    const data = await handleResponse<BackendConsultationResponse | null>(res);
    if (!data) return null;

    const mapped = mapBackendConsultationToFrontend(data);
    ACTIVE_LOCAL_NOTES = {
      notes: mapped.clinicalNotes || "",
      diagnosis: mapped.diagnosis || "",
      prescriptions: [...mapped.prescriptions],
      followUp: mapped.followUpRecommendation || "",
    };
    return mapped;
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/start
   * Authoritatively starts or resumes the consultation.
   */
  async startNewConsultation(
    queueEntryId: string,
    _patientId?: string,
    _patientName?: string,
    _doctorId?: string,
    _doctorName?: string
  ): Promise<Consultation> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(queueEntryId)}/start`,
      {
        method: "POST",
        headers,
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    const mapped = mapBackendConsultationToFrontend(data);
    ACTIVE_LOCAL_NOTES = {
      notes: mapped.clinicalNotes || "",
      diagnosis: mapped.diagnosis || "",
      prescriptions: [...mapped.prescriptions],
      followUp: mapped.followUpRecommendation || "",
    };
    return mapped;
  }

  /**
   * PUT /api/v1/queues/consultation/{consultation_id}/notes
   * Authoritatively persists clinical notes and prescriptions to the database.
   */
  async saveConsultationNotes(
    consultationId: string,
    payload: {
      clinicalNotes?: string;
      diagnosis?: string;
      prescriptions?: string[];
      followUpRecommendation?: string;
    }
  ): Promise<Consultation> {
    const headers = await getAuthHeaders();
    const body = {
      clinical_notes: payload.clinicalNotes,
      diagnosis: payload.diagnosis,
      prescriptions: payload.prescriptions ? JSON.stringify(payload.prescriptions) : undefined,
      follow_up_instructions: payload.followUpRecommendation,
    };

    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/consultation/${encodeURIComponent(consultationId)}/notes`,
      {
        method: "PUT",
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      }
    );

    const data = await handleResponse<BackendConsultationResponse>(res);
    const mapped = mapBackendConsultationToFrontend(data);
    ACTIVE_LOCAL_NOTES = {
      notes: mapped.clinicalNotes || "",
      diagnosis: mapped.diagnosis || "",
      prescriptions: [...mapped.prescriptions],
      followUp: mapped.followUpRecommendation || "",
    };
    return mapped;
  }

  updateNotes(notes: string): void {
    ACTIVE_LOCAL_NOTES.notes = notes;
  }

  updateDiagnosis(diagnosis: string): void {
    ACTIVE_LOCAL_NOTES.diagnosis = diagnosis;
  }

  addPrescription(rx: string): void {
    if (rx.trim()) {
      ACTIVE_LOCAL_NOTES.prescriptions.push(rx.trim());
    }
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/complete
   * Authoritatively completes the active consultation on backend.
   */
  async completeConsultation(
    queueEntryId?: string,
    notesPayload?: {
      clinicalNotes?: string;
      diagnosis?: string;
      prescriptions?: string[];
      followUpRecommendation?: string;
    }
  ): Promise<Consultation | null> {
    let targetEntryId = queueEntryId;
    if (!targetEntryId) {
      const active = await this.getActiveConsultation();
      if (!active) return null;
      targetEntryId = active.queueEntryId;
    }

    const headers = await getAuthHeaders();
    let body: Record<string, unknown> | undefined = undefined;

    if (notesPayload) {
      body = {
        clinical_notes: notesPayload.clinicalNotes ?? ACTIVE_LOCAL_NOTES.notes,
        diagnosis: notesPayload.diagnosis ?? ACTIVE_LOCAL_NOTES.diagnosis,
        prescriptions: notesPayload.prescriptions
          ? JSON.stringify(notesPayload.prescriptions)
          : ACTIVE_LOCAL_NOTES.prescriptions.length > 0
          ? JSON.stringify(ACTIVE_LOCAL_NOTES.prescriptions)
          : undefined,
        follow_up_instructions:
          notesPayload.followUpRecommendation ?? ACTIVE_LOCAL_NOTES.followUp,
      };
    } else if (
      ACTIVE_LOCAL_NOTES.notes ||
      ACTIVE_LOCAL_NOTES.diagnosis ||
      ACTIVE_LOCAL_NOTES.prescriptions.length > 0 ||
      ACTIVE_LOCAL_NOTES.followUp
    ) {
      body = {
        clinical_notes: ACTIVE_LOCAL_NOTES.notes,
        diagnosis: ACTIVE_LOCAL_NOTES.diagnosis,
        prescriptions:
          ACTIVE_LOCAL_NOTES.prescriptions.length > 0
            ? JSON.stringify(ACTIVE_LOCAL_NOTES.prescriptions)
            : undefined,
        follow_up_instructions: ACTIVE_LOCAL_NOTES.followUp,
      };
    }

    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(targetEntryId)}/complete`,
      {
        method: "POST",
        headers: {
          ...headers,
          ...(body ? { "Content-Type": "application/json" } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    ACTIVE_LOCAL_NOTES = { notes: "", diagnosis: "", prescriptions: [], followUp: "" };
    return mapBackendConsultationToFrontend(data);
  }
}

export const consultationService = new ConsultationService();
