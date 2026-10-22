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
} = {
  notes: "",
  diagnosis: "",
  prescriptions: [],
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
    mapped.clinicalNotes = ACTIVE_LOCAL_NOTES.notes;
    mapped.diagnosis = ACTIVE_LOCAL_NOTES.diagnosis;
    mapped.prescriptions = [...ACTIVE_LOCAL_NOTES.prescriptions];
    return mapped;
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/start
   * Authoritatively starts the consultation.
   */
  async startNewConsultation(
    queueEntryId: string,
    _patientId?: string,
    _patientName?: string,
    _doctorId?: string,
    _doctorName?: string
  ): Promise<Consultation> {
    ACTIVE_LOCAL_NOTES = { notes: "", diagnosis: "", prescriptions: [] };
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(queueEntryId)}/start`,
      {
        method: "POST",
        headers,
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    return mapBackendConsultationToFrontend(data);
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
  async completeConsultation(queueEntryId?: string): Promise<Consultation | null> {
    let targetEntryId = queueEntryId;
    if (!targetEntryId) {
      const active = await this.getActiveConsultation();
      if (!active) return null;
      targetEntryId = active.queueEntryId;
    }

    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(targetEntryId)}/complete`,
      {
        method: "POST",
        headers,
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    ACTIVE_LOCAL_NOTES = { notes: "", diagnosis: "", prescriptions: [] };
    return mapBackendConsultationToFrontend(data);
  }
}

export const consultationService = new ConsultationService();
