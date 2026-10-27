import { QueueEntry, QueueStatus, Consultation } from "@/types";
import { getAuthHeaders } from "@/services/doctors";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class QueueApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "QueueApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export interface BackendWaitEstimate {
  lower_minutes: number;
  expected_minutes: number;
  upper_minutes: number;
  source: string;
}

export interface BackendQueueEntryResponse {
  id: string;
  appointment_id: string;
  patient_id: string;
  doctor_id: string;
  hospital_id: string;
  queue_date: string;
  token_number: string;
  status: string; // WAITING, CALLED, IN_CONSULTATION, COMPLETED, NO_SHOW, CANCELLED
  checked_in_at: string;
  called_at?: string | null;
  consultation_started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  patient_name?: string | null;
  patient_gender?: string | null;
  patient_age?: number | null;
  doctor_name?: string | null;
  room_number?: string | null;
  department_name?: string | null;
  chief_complaint?: string | null;
}

export interface BackendPatientQueueStatusResponse {
  queue_entry_id: string;
  appointment_id: string;
  doctor_id: string;
  hospital_id: string;
  token_number: string;
  status: string;
  checked_in_at: string;
  called_at?: string | null;
  consultation_started_at?: string | null;
  patients_ahead: number;
  wait_estimate: BackendWaitEstimate;
  patient_name?: string | null;
  doctor_name?: string | null;
  room_number?: string | null;
  department_name?: string | null;
  chief_complaint?: string | null;
}

export interface BackendConsultationResponse {
  id: string;
  queue_entry_id: string;
  appointment_id: string;
  patient_id: string;
  doctor_id: string;
  hospital_id: string;
  started_at: string;
  completed_at?: string | null;
  status: string; // IN_PROGRESS, COMPLETED
  duration_seconds?: number | null;
  created_at: string;
  updated_at: string;
  patient_name?: string | null;
  doctor_name?: string | null;
  token_number?: string | null;
  chief_complaint?: string | null;
  clinical_notes?: string | null;
  diagnosis?: string | null;
  prescriptions?: string | null;
  follow_up_instructions?: string | null;
}

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

export function formatTimeLabel(isoString?: string | null): string {
  if (!isoString) return "";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return isoString;
  }
}

export function mapBackendStatusToFrontend(rawStatus: string): QueueStatus {
  const norm = (rawStatus || "").toUpperCase();
  switch (norm) {
    case "CALLED":
      return "called";
    case "IN_CONSULTATION":
    case "IN_PROGRESS":
      return "in_consultation";
    case "COMPLETED":
      return "completed";
    case "NO_SHOW":
      return "no_show";
    case "WAITING":
    case "CHECKED_IN":
    default:
      return "waiting";
  }
}

export function mapBackendQueueEntryToFrontend(
  entry: BackendQueueEntryResponse,
  index: number = 0
): QueueEntry {
  const status = mapBackendStatusToFrontend(entry.status);
  const minTime = Math.max(5, index * 10);
  const maxTime = Math.max(10, index * 18 + 5);

  return {
    id: entry.id,
    token: entry.token_number,
    patientId: entry.patient_id,
    patientName: entry.patient_name || "Patient",
    patientAge: entry.patient_age ?? undefined,
    patientGender: entry.patient_gender ?? undefined,
    doctorId: entry.doctor_id,
    doctorName: entry.doctor_name || "Doctor",
    department: entry.department_name || "Outpatient Clinic",
    roomNumber: entry.room_number || "Room 204",
    appointmentId: entry.appointment_id,
    status,
    positionAhead: index,
    estimatedWaitMinutes: {
      min: minTime,
      max: maxTime,
    },
    triageUrgency: "routine",
    chiefComplaint: entry.chief_complaint || "Outpatient Clinical Consultation",
    checkInTime: formatTimeLabel(entry.checked_in_at),
    calledTime: entry.called_at ? formatTimeLabel(entry.called_at) : undefined,
    consultationStartTime: entry.consultation_started_at
      ? formatTimeLabel(entry.consultation_started_at)
      : undefined,
    consultationEndTime: entry.completed_at
      ? formatTimeLabel(entry.completed_at)
      : undefined,
    updatedAt: entry.updated_at || new Date().toISOString(),
  };
}

export function mapBackendPatientQueueToFrontend(
  statusResp: BackendPatientQueueStatusResponse
): QueueEntry {
  const status = mapBackendStatusToFrontend(statusResp.status);

  return {
    id: statusResp.queue_entry_id,
    token: statusResp.token_number,
    patientId: "", // Authoritatively resolved via /patients/me
    patientName: statusResp.patient_name || "You",
    doctorId: statusResp.doctor_id,
    doctorName: statusResp.doctor_name || "Doctor",
    department: statusResp.department_name || "Adult Outpatient Clinic",
    roomNumber: statusResp.room_number || "Room 204",
    appointmentId: statusResp.appointment_id,
    status,
    positionAhead: statusResp.patients_ahead,
    estimatedWaitMinutes: {
      min: statusResp.wait_estimate?.lower_minutes ?? 5,
      max: statusResp.wait_estimate?.upper_minutes ?? 15,
    },
    triageUrgency: "routine",
    chiefComplaint: statusResp.chief_complaint || "Outpatient Consultation",
    checkInTime: formatTimeLabel(statusResp.checked_in_at),
    calledTime: statusResp.called_at ? formatTimeLabel(statusResp.called_at) : undefined,
    consultationStartTime: statusResp.consultation_started_at
      ? formatTimeLabel(statusResp.consultation_started_at)
      : undefined,
    updatedAt: new Date().toISOString(),
  };
}

export function mapBackendConsultationToFrontend(
  raw: BackendConsultationResponse
): Consultation {
  const now = Date.now();
  const startTime = raw.started_at;
  const elapsed = startTime
    ? Math.max(0, Math.floor((now - new Date(startTime).getTime()) / 1000))
    : 0;

  let parsedPrescriptions: string[] = [];
  if (raw.prescriptions) {
    try {
      const parsed = JSON.parse(raw.prescriptions);
      if (Array.isArray(parsed)) {
        parsedPrescriptions = parsed.map(String);
      } else {
        parsedPrescriptions = [raw.prescriptions];
      }
    } catch {
      parsedPrescriptions = raw.prescriptions
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
    }
  }

  return {
    id: raw.id,
    queueEntryId: raw.queue_entry_id,
    appointmentId: raw.appointment_id,
    patientId: raw.patient_id,
    patientName: raw.patient_name || "Patient",
    doctorId: raw.doctor_id,
    doctorName: raw.doctor_name || "Doctor",
    status: raw.status === "COMPLETED" ? "completed" : "active",
    startTime: raw.started_at,
    endTime: raw.completed_at || undefined,
    elapsedSeconds: raw.duration_seconds ?? elapsed,
    expectedDurationRange: { min: 12, max: 18 },
    clinicalNotes: raw.clinical_notes || "",
    diagnosis: raw.diagnosis || "",
    prescriptions: parsedPrescriptions,
    followUpRecommendation: raw.follow_up_instructions || "",
    intakeSummary: {
      chiefComplaint: raw.chief_complaint || "Outpatient Consultation",
    },
  };
}

export class QueueService {
  /**
   * GET /api/v1/patients/me/queue
   * Retrieves the authenticated patient's active queue status.
   * Returns null if patient has no active queue token (HTTP 404).
   */
  async getPatientActiveQueue(_patientId?: string): Promise<QueueEntry | null> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/patients/me/queue`, {
      method: "GET",
      headers,
    });

    if (res.status === 404) {
      try {
        const data = await res.json();
        // Check for legitimate empty queue code
        if (data?.error?.code === "NO_ACTIVE_QUEUE_ENTRY") {
          return null;
        }
        // Genuine 404 error (e.g. PATIENT_PROFILE_NOT_FOUND or unknown endpoint)
        throw new QueueApiError(
          data?.error?.message || "Patient profile not found",
          404,
          data?.error?.code,
          data
        );
      } catch (err) {
        if (err instanceof QueueApiError) throw err;
        return null;
      }
    }

    const data = await handleResponse<BackendPatientQueueStatusResponse>(res);
    return mapBackendPatientQueueToFrontend(data);
  }

  /**
   * GET /api/v1/queues/{doctor_id}/current
   * Retrieves the live waiting and called queue for the doctor.
   */
  async getDoctorQueue(doctorId: string = "me"): Promise<QueueEntry[]> {
    const headers = await getAuthHeaders();
    const target = doctorId ? encodeURIComponent(doctorId) : "me";
    const res = await fetch(`${API_BASE_URL}/api/v1/queues/${target}/current`, {
      method: "GET",
      headers,
    });
    const list = await handleResponse<BackendQueueEntryResponse[]>(res);
    return list.map((entry, idx) => mapBackendQueueEntryToFrontend(entry, idx));
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/call
   * Authoritatively transitions queue entry to CALLED.
   */
  async callPatient(queueEntryId: string): Promise<QueueEntry> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(queueEntryId)}/call`,
      {
        method: "POST",
        headers,
      }
    );
    const data = await handleResponse<BackendQueueEntryResponse>(res);
    return mapBackendQueueEntryToFrontend(data);
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/start
   * Authoritatively starts the consultation and activates Consultation record.
   */
  async startConsultation(queueEntryId: string): Promise<Consultation> {
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

  /**
   * GET /api/v1/queues/consultation/{queue_entry_id}
   * Retrieves consultation by queue entry id.
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
    const data = await handleResponse<BackendConsultationResponse>(res);
    return mapBackendConsultationToFrontend(data);
  }

  /**
   * PUT /api/v1/queues/consultation/{consultation_id}/notes
   * Authoritatively persists clinical notes for an active consultation.
   */
  async saveConsultationNotes(
    consultationId: string,
    notes: {
      clinical_notes?: string;
      diagnosis?: string;
      prescriptions?: string;
      follow_up_instructions?: string;
    }
  ): Promise<Consultation> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/consultation/${encodeURIComponent(consultationId)}/notes`,
      {
        method: "PUT",
        headers: {
          ...headers,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(notes),
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    return mapBackendConsultationToFrontend(data);
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/complete
   * Authoritatively completes the consultation, queue entry, and appointment.
   */
  async completeConsultation(
    queueEntryId: string,
    notes?: {
      clinical_notes?: string;
      diagnosis?: string;
      prescriptions?: string;
      follow_up_instructions?: string;
    }
  ): Promise<Consultation> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(queueEntryId)}/complete`,
      {
        method: "POST",
        headers: {
          ...headers,
          ...(notes ? { "Content-Type": "application/json" } : {}),
        },
        body: notes ? JSON.stringify(notes) : undefined,
      }
    );
    const data = await handleResponse<BackendConsultationResponse>(res);
    return mapBackendConsultationToFrontend(data);
  }

  /**
   * POST /api/v1/queues/{queue_entry_id}/no-show
   * Authoritatively marks the queue entry as NO_SHOW.
   */
  async markNoShow(queueEntryId: string): Promise<QueueEntry> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/queues/${encodeURIComponent(queueEntryId)}/no-show`,
      {
        method: "POST",
        headers,
      }
    );
    const data = await handleResponse<BackendQueueEntryResponse>(res);
    return mapBackendQueueEntryToFrontend(data);
  }

  /**
   * Convenience alias for doctor's queue.
   */
  async getAllQueue(): Promise<QueueEntry[]> {
    return this.getDoctorQueue("me");
  }


  /**
   * Subscription helper that polls periodically or notifies listeners.
   */
  subscribe(listener: (entries: QueueEntry[]) => void): () => void {
    let isActive = true;
    const poll = async () => {
      try {
        const data = await this.getDoctorQueue("me");
        if (isActive) {
          listener(data);
        }
      } catch {
        // Poll failure; wait for next cycle
      }
    };

    poll();
    const timer = setInterval(poll, 8000);

    return () => {
      isActive = false;
      clearInterval(timer);
    };
  }

  /**
   * Subscription helper that polls periodically for the authenticated patient's active queue status.
   * Strictly queries the patient-facing endpoint GET /api/v1/patients/me/queue.
   */
  subscribePatient(
    listener: (entry: QueueEntry | null) => void,
    intervalMs: number = 8000
  ): () => void {
    let isActive = true;
    const poll = async () => {
      try {
        const data = await this.getPatientActiveQueue();
        if (isActive) {
          listener(data);
        }
      } catch {
        // Poll failure; wait for next cycle
      }
    };

    poll();
    const timer = setInterval(poll, intervalMs);

    return () => {
      isActive = false;
      clearInterval(timer);
    };
  }
}

export const queueService = new QueueService();
