import { Appointment, AppointmentStatus } from "@/types";
import { getAuthHeaders } from "@/services/doctors";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class AppointmentApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;

  constructor(message: string, status: number, code?: string, detail?: unknown) {
    super(message);
    this.name = "AppointmentApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export interface AppointmentCreateRequest {
  patient_id: string;
  doctor_id: string;
  hospital_id: string;
  appointment_date: string; // YYYY-MM-DD
  scheduled_start: string;  // HH:MM:SS
  scheduled_end: string;    // HH:MM:SS
  appointment_type?: string;
  reason?: string | null;
}

export interface BackendAppointmentResponse {
  id: string;
  patient_id: string;
  doctor_id: string;
  hospital_id: string;
  appointment_date: string;
  scheduled_start: string;
  scheduled_end: string;
  appointment_type: string;
  reason?: string | null;
  status: "BOOKED" | "CONFIRMED" | "CANCELLED" | "COMPLETED" | "NO_SHOW" | string;
  created_at: string;
  updated_at: string;
  doctor_name?: string | null;
  doctor_specialty?: string | null;
  department_name?: string | null;
  queue_token?: string | null;
}

export interface QueueEntryResponse {
  id: string;
  appointment_id: string;
  patient_id: string;
  doctor_id: string;
  hospital_id: string;
  queue_date: string;
  token_number: string;
  status: string;
  checked_in_at: string;
  called_at?: string | null;
  consultation_started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PatientProfileResponse {
  id: string;
  profile_id: string;
  date_of_birth: string;
  preferred_language: string;
  emergency_contact?: string | null;
  accessibility_notes?: string | null;
  created_at: string;
  updated_at: string;
  profile: {
    id: string;
    auth_user_id: string;
    role: string;
    full_name: string;
    phone?: string | null;
    email: string;
    hospital_id?: string | null;
  };
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
          errorMessage = data.detail.map((d: { msg?: string; loc?: unknown[] }) => d.msg).join("; ");
          errorCode = "VALIDATION_ERROR";
        } else {
          errorMessage = JSON.stringify(data.detail);
        }
      }
    } catch {
      // Response was not JSON
    }

    throw new AppointmentApiError(errorMessage, res.status, errorCode, detail);
  }
  return res.json() as Promise<T>;
}

export function formatAppointmentDate(isoDate: string): string {
  if (!isoDate) return "Scheduled Date";
  try {
    const parts = isoDate.split("-");
    if (parts.length === 3) {
      const year = parseInt(parts[0], 10);
      const month = parseInt(parts[1], 10) - 1;
      const day = parseInt(parts[2], 10);
      const d = new Date(year, month, day);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    }
    const d = new Date(isoDate);
    return isNaN(d.getTime())
      ? isoDate
      : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  } catch {
    return isoDate;
  }
}

export function formatTimeSlot(timeStr: string): string {
  if (!timeStr) return "";
  try {
    const parts = timeStr.split(":");
    if (parts.length >= 2) {
      let hours = parseInt(parts[0], 10);
      const minutes = parts[1];
      const ampm = hours >= 12 ? "PM" : "AM";
      hours = hours % 12;
      hours = hours ? hours : 12;
      return `${hours}:${minutes} ${ampm}`;
    }
    return timeStr;
  } catch {
    return timeStr;
  }
}

export function mapBackendStatusToFrontend(
  backendStatus: string,
  hasQueueToken?: boolean
): AppointmentStatus {
  const norm = (backendStatus || "").toUpperCase();
  if (norm === "CANCELLED") return "cancelled";
  if (norm === "COMPLETED") return "completed";
  if (norm === "NO_SHOW") return "no_show";
  if (norm === "CONFIRMED" || norm === "BOOKED") {
    return hasQueueToken ? "checked_in" : "scheduled";
  }
  return "scheduled";
}

export function mapBackendAppointmentToFrontend(
  backendAppt: BackendAppointmentResponse
): Appointment {
  const hasToken = Boolean(backendAppt.queue_token);
  const displayStatus = mapBackendStatusToFrontend(backendAppt.status, hasToken);
  const displayDate = formatAppointmentDate(backendAppt.appointment_date);
  const displayTime = formatTimeSlot(backendAppt.scheduled_start);

  return {
    id: backendAppt.id,
    patientId: backendAppt.patient_id,
    doctorId: backendAppt.doctor_id,
    doctorName: backendAppt.doctor_name || `Doctor (${backendAppt.doctor_id.slice(0, 8)})`,
    doctorSpecialty: backendAppt.doctor_specialty || "Outpatient Specialist",
    department: backendAppt.department_name || "Outpatient Clinic",
    date: displayDate,
    timeSlot: displayTime,
    status: displayStatus,
    reasonForVisit: backendAppt.reason || "Outpatient Consultation",
    createdAt: backendAppt.created_at,
    queueToken: backendAppt.queue_token || undefined,
    hospitalId: backendAppt.hospital_id,
    scheduledStart: backendAppt.scheduled_start,
    scheduledEnd: backendAppt.scheduled_end,
    appointmentDate: backendAppt.appointment_date,
    rawStatus: backendAppt.status,
  };
}

export class AppointmentService {
  /**
   * GET /api/v1/patients/me
   * Resolves the current authenticated patient's profile and database ID.
   */
  async getCurrentPatient(): Promise<PatientProfileResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/patients/me`, {
      method: "GET",
      headers,
    });
    return handleResponse<PatientProfileResponse>(res);
  }

  /**
   * POST /api/v1/appointments
   * Books a concrete appointment slot with calendar conflict checking.
   */
  async bookAppointment(
    data: AppointmentCreateRequest
  ): Promise<BackendAppointmentResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/appointments`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        patient_id: data.patient_id,
        doctor_id: data.doctor_id,
        hospital_id: data.hospital_id,
        appointment_date: data.appointment_date,
        scheduled_start: data.scheduled_start,
        scheduled_end: data.scheduled_end,
        appointment_type: data.appointment_type || "in_person",
        reason: data.reason || null,
      }),
    });
    return handleResponse<BackendAppointmentResponse>(res);
  }

  /**
   * GET /api/v1/appointments
   * Lists appointments for the authenticated user, mapped to frontend display models.
   */
  async listAppointments(patientId?: string): Promise<Appointment[]> {
    const headers = await getAuthHeaders();
    const query = new URLSearchParams();
    if (patientId) {
      query.append("patient_id", patientId);
    }
    const queryString = query.toString() ? `?${query.toString()}` : "";
    const res = await fetch(`${API_BASE_URL}/api/v1/appointments${queryString}`, {
      method: "GET",
      headers,
    });
    const backendList = await handleResponse<BackendAppointmentResponse[]>(res);
    return backendList.map(mapBackendAppointmentToFrontend);
  }

  /**
   * Convenience alias for listAppointments.
   */
  async getAppointmentsByPatient(patientId?: string): Promise<Appointment[]> {
    return this.listAppointments(patientId);
  }

  /**
   * Convenience method to fetch all appointments accessible by the user.
   */
  async getAllAppointments(): Promise<Appointment[]> {
    return this.listAppointments();
  }

  /**
   * Retrieves the next upcoming scheduled or checked-in appointment.
   */
  async getUpcomingAppointment(patientId?: string): Promise<Appointment | undefined> {
    const list = await this.listAppointments(patientId);
    return list.find(
      (a) => a.status === "scheduled" || a.status === "checked_in"
    );
  }

  /**
   * GET /api/v1/appointments/{appointment_id}
   */
  async getAppointment(appointmentId: string): Promise<BackendAppointmentResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/appointments/${encodeURIComponent(appointmentId)}`,
      {
        method: "GET",
        headers,
      }
    );
    return handleResponse<BackendAppointmentResponse>(res);
  }

  /**
   * POST /api/v1/appointments/{appointment_id}/cancel
   * Authoritatively cancels an appointment in the backend database.
   */
  async cancelAppointment(
    appointmentId: string,
    _reason?: string
  ): Promise<BackendAppointmentResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/appointments/${encodeURIComponent(appointmentId)}/cancel`,
      {
        method: "POST",
        headers,
      }
    );
    return handleResponse<BackendAppointmentResponse>(res);
  }

  /**
   * Update appointment status transition helper.
   */
  async updateAppointmentStatus(
    appointmentId: string,
    status: AppointmentStatus
  ): Promise<void> {
    if (status === "cancelled") {
      await this.cancelAppointment(appointmentId);
    } else if (status === "checked_in") {
      await this.checkInAppointment(appointmentId);
    }
  }

  /**
   * POST /api/v1/appointments/{appointment_id}/check-in
   * Authoritatively checks in an appointment and generates the live queue token.
   */
  async checkInAppointment(appointmentId: string): Promise<QueueEntryResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/appointments/${encodeURIComponent(appointmentId)}/check-in`,
      {
        method: "POST",
        headers,
      }
    );
    return handleResponse<QueueEntryResponse>(res);
  }
}

export const appointmentService = new AppointmentService();
