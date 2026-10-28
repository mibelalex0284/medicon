import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { Doctor, DoctorWorkload } from "@/types";

export interface DoctorRecommendationRequest {
  hospital_id?: string | null;
  specialty_id?: string | null;
  triage_session_id?: string | null;
  consultation_mode?: string | null;
  appointment_date?: string | null;
  preferred_doctor_id?: string | null;
  preferred_language?: string | null;
  require_availability?: boolean;
  limit?: number;
}

export interface RecommendationFactorBreakdown {
  specialty_match: boolean;
  specialty_is_primary: boolean;
  specialty_score: number;
  has_available_slots: boolean;
  available_slot_count: number;
  availability_score: number;
  estimated_wait_minutes: number;
  wait_score: number;
  years_of_experience: number;
  experience_score: number;
  average_rating: number;
  rating_count: number;
  rating_reliability_score?: number;
  preference_match: boolean;
  preference_score: number;
  language_match: boolean;
  language_score?: number;
  raw_weights?: Record<string, number>;
}

export interface ProfileResponse {
  id: string;
  auth_user_id: string;
  role: string;
  full_name: string;
  email: string;
  phone?: string | null;
  avatar_url?: string | null;
}

export interface HospitalResponse {
  id: string;
  name: string;
  code: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  is_active: boolean;
}

export interface DepartmentResponse {
  id: string;
  hospital_id: string;
  name: string;
  code: string;
  description?: string | null;
  is_active: boolean;
}

export interface SpecialtyResponse {
  id: string;
  name: string;
  code: string;
  description?: string | null;
  is_active: boolean;
}

export interface DoctorSpecialtyResponse {
  id: string;
  doctor_id: string;
  specialty_id: string;
  is_primary: boolean;
  specialty?: SpecialtyResponse | null;
}

export interface RecommendedDoctorProfile {
  id: string;
  profile_id: string;
  hospital_id: string;
  department_id?: string | null;
  license_number: string;
  years_of_experience: number;
  consultation_mode: string;
  average_rating: number;
  rating_count: number;
  languages: string;
  is_active: boolean;
  profile: ProfileResponse;
  hospital?: HospitalResponse | null;
  department?: DepartmentResponse | null;
  specialties: DoctorSpecialtyResponse[];
  invitation_status?: string | null;
  is_accepting_patients?: boolean;
}

export interface DoctorIntakeStatusResponse {
  doctor_id: string;
  is_accepting_patients: boolean;
  status: string;
  message: string;
}

export type DoctorResponse = RecommendedDoctorProfile;

export interface DoctorRecommendationItem {
  doctor_id: string;
  rank: number;
  score: number;
  estimated_wait_minutes: number;
  consultation_mode: string;
  matched_factors: string[];
  explanation: string;
  doctor: RecommendedDoctorProfile;
  factor_breakdown: RecommendationFactorBreakdown;
}

export interface DoctorRecommendationResponse {
  recommendations: DoctorRecommendationItem[];
  status: "SUCCESS" | "NO_ELIGIBLE_DOCTORS" | "EMERGENCY_ESCALATION" | string;
  message: string;
  applied_specialty_id?: string | null;
  applied_specialty_name?: string | null;
  applied_hospital_id: string;
  total_eligible_doctors: number;
  is_emergency_escalation: boolean;
  escalation_notice?: string | null;
  urgency?: "LOW" | "MODERATE" | "HIGH" | string | null;
}

export interface AvailableSlot {
  start_time: string;
  end_time: string;
  is_available: boolean;
}

export interface DoctorAvailabilityResponse {
  doctor_id: string;
  hospital_id: string;
  appointment_date: string;
  slot_duration_minutes: number;
  has_schedule?: boolean;
  schedule_configured?: boolean;
  is_fully_booked?: boolean;
  next_available_date?: string | null;
  slots: AvailableSlot[];
}

export interface DoctorScheduleItem {
  id?: string;
  doctor_id?: string;
  hospital_id?: string;
  day_of_week: number;
  start_time: string;
  end_time: string;
  slot_duration_minutes: number;
  is_active: boolean;
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English",
  es: "Spanish",
  hi: "Hindi",
  ml: "Malayalam",
  fr: "French",
  ar: "Arabic",
  de: "German",
  zh: "Mandarin",
  ta: "Tamil",
  te: "Telugu",
  bn: "Bengali",
};

export function formatDoctorLanguages(langStr?: string | null): string {
  if (!langStr) return "English";
  return (
    langStr
      .split(",")
      .map((code) => {
        const clean = code.trim().toLowerCase();
        return (
          LANGUAGE_NAMES[clean] ||
          (clean.length > 0 ? clean.charAt(0).toUpperCase() + clean.slice(1) : "")
        );
      })
      .filter(Boolean)
      .join(", ") || "English"
  );
}

export function getDoctorInitials(name?: string | null): string {
  if (!name) return "DR";
  const clean = name
    .replace(/\b(Dr|Doctor|MD|MBBS|PhD|MS|DO)\b/gi, "")
    .replace(/[^a-zA-Z\s]/g, "")
    .trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "DR";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function formatDoctorSpecialties(doctor?: DoctorResponse | null): string {
  if (!doctor || !doctor.specialties || doctor.specialties.length === 0) {
    return "General Medicine";
  }
  const specNames = doctor.specialties
    .map((s) => s.specialty?.name)
    .filter(Boolean) as string[];
  return specNames.length > 0 ? specNames.join(" & ") : "General Medicine";
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function getAuthHeaders(): Promise<Record<string, string>> {
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

export class DoctorApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "DoctorApiError";
    this.status = status;
    this.code = code;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errorMessage = `HTTP error ${res.status}`;
    let errorCode: string | undefined;
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
      // Non-JSON response
    }
    throw new DoctorApiError(errorMessage, res.status, errorCode);
  }
  return res.json() as Promise<T>;
}

export interface DoctorLifecycleResponse {
  doctor_id: string;
  profile_id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  status: "active" | "deactivated" | "deleted";
  message: string;
}

export interface AdminResendInvitationResponse {
  doctor_id: string;
  profile_id: string;
  full_name: string;
  email: string;
  action_link?: string | null;
  message: string;
  auth_provisioned: boolean;
}

export class DoctorService {
  /**
   * POST /api/v1/doctors/recommend
   * Recommends and ranks eligible doctors based on triage session or direct specialty.
   */
  async recommendDoctors(
    request: DoctorRecommendationRequest
  ): Promise<DoctorRecommendationResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/doctors/recommend`, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
    });
    return handleResponse<DoctorRecommendationResponse>(res);
  }

  /**
   * GET /api/v1/doctors/{doctor_id}/availability
   * Retrieves discrete available appointment slots for a doctor on a specific date.
   */
  async getDoctorAvailability(
    doctorId: string,
    appointmentDate: string,
    slotDurationMinutes?: number
  ): Promise<DoctorAvailabilityResponse> {
    const headers = await getAuthHeaders();
    const query = new URLSearchParams({ appointment_date: appointmentDate });
    if (slotDurationMinutes) {
      query.append("slot_duration_minutes", slotDurationMinutes.toString());
    }
    const res = await fetch(
      `${API_BASE_URL}/api/v1/doctors/${encodeURIComponent(doctorId)}/availability?${query.toString()}`,
      {
        method: "GET",
        headers,
      }
    );
    return handleResponse<DoctorAvailabilityResponse>(res);
  }

  /**
   * GET /api/v1/doctors/me
   * Authoritatively retrieves the authenticated doctor profile.
   */
  async getCurrentDoctor(): Promise<DoctorResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/doctors/me`, {
      method: "GET",
      headers,
    });
    return handleResponse<DoctorResponse>(res);
  }

  /**
   * PATCH /api/v1/doctors/{doctorId}/intake-status
   * Updates clinic station patient intake availability.
   */
  async updateIntakeStatus(
    doctorId: string,
    isAcceptingPatients: boolean
  ): Promise<DoctorIntakeStatusResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/doctors/${encodeURIComponent(doctorId)}/intake-status`,
      {
        method: "PATCH",
        headers,
        body: JSON.stringify({ is_accepting_patients: isAcceptingPatients }),
      }
    );
    return handleResponse<DoctorIntakeStatusResponse>(res);
  }

  /**
   * GET /api/v1/doctors/admin/list
   * Authoritatively retrieves registered doctors for admin directory.
   */
  async listDoctorsAdmin(
    hospitalId?: string,
    status?: "all" | "active" | "inactive"
  ): Promise<DoctorResponse[]> {
    const headers = await getAuthHeaders();
    const params = new URLSearchParams();
    if (hospitalId) params.append("hospital_id", hospitalId);
    if (status && status !== "all") params.append("status", status);
    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE_URL}/api/v1/doctors/admin/list${query}`, {
      method: "GET",
      headers,
    });
    return handleResponse<DoctorResponse[]>(res);
  }

  /**
   * PATCH /api/v1/admin/doctors/{doctorId}/status
   * Deactivates or reactivates a doctor account.
   */
  async updateDoctorStatus(
    doctorId: string,
    isActive: boolean,
    reason?: string
  ): Promise<DoctorLifecycleResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/doctors/${encodeURIComponent(doctorId)}/status`, {
      method: "PATCH",
      headers,
      body: JSON.stringify({ is_active: isActive, reason: reason || null }),
    });
    return handleResponse<DoctorLifecycleResponse>(res);
  }

  /**
   * DELETE /api/v1/admin/doctors/{doctorId}
   * Safely deletes a doctor record if zero dependent clinical records exist.
   */
  async deleteDoctor(doctorId: string): Promise<DoctorLifecycleResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/doctors/${encodeURIComponent(doctorId)}`, {
      method: "DELETE",
      headers,
    });
    return handleResponse<DoctorLifecycleResponse>(res);
  }

  /**
   * POST /api/v1/admin/doctors/{doctorId}/resend-invitation
   * Safely regenerates an invitation or password setup link without duplicate records.
   */
  async resendDoctorInvitation(doctorId: string): Promise<AdminResendInvitationResponse> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/doctors/${encodeURIComponent(doctorId)}/resend-invitation`, {
      method: "POST",
      headers,
    });
    return handleResponse<AdminResendInvitationResponse>(res);
  }

  /**
   * GET /api/v1/hospitals
   * Lists active hospitals for admin assignment and tenant filtering.
   */
  async listHospitals(): Promise<HospitalResponse[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/hospitals`, {
      method: "GET",
      headers,
    });
    return handleResponse<HospitalResponse[]>(res);
  }

  /**
   * GET /api/v1/departments
   * Lists departments, optionally filtered by hospital ID.
   */
  async listDepartments(hospitalId?: string): Promise<DepartmentResponse[]> {
    const headers = await getAuthHeaders();
    const query = hospitalId ? `?hospital_id=${encodeURIComponent(hospitalId)}` : "";
    const res = await fetch(`${API_BASE_URL}/api/v1/departments${query}`, {
      method: "GET",
      headers,
    });
    return handleResponse<DepartmentResponse[]>(res);
  }

  /**
   * GET /api/v1/specialties
   * Lists all active clinical specialties.
   */
  async listSpecialties(): Promise<SpecialtyResponse[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/specialties`, {
      method: "GET",
      headers,
    });
    return handleResponse<SpecialtyResponse[]>(res);
  }

  /**
   * GET /api/v1/admin/doctors/{doctorId}/schedules
   * Retrieves configured weekly consultation schedules for a physician.
   */
  async getDoctorSchedules(doctorId: string): Promise<DoctorScheduleItem[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/doctors/${doctorId}/schedules`, {
      method: "GET",
      headers,
    });
    return handleResponse<DoctorScheduleItem[]>(res);
  }

  /**
   * PUT /api/v1/admin/doctors/{doctorId}/schedules
   * Updates weekly consultation schedule slots for a physician.
   */
  async updateDoctorSchedules(
    doctorId: string,
    schedules: DoctorScheduleItem[]
  ): Promise<DoctorScheduleItem[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/doctors/${doctorId}/schedules`, {
      method: "PUT",
      headers: {
        ...headers,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ schedules }),
    });
    return handleResponse<DoctorScheduleItem[]>(res);
  }

  /**
   * POST /api/v1/admin/doctors/{doctorId}/schedules/initialize-default
   * Initializes standard outpatient consultation hours (Mon-Fri 09:00 - 17:00, 30 min slots) for a physician.
   */
  async initializeDefaultSchedule(
    doctorId: string,
    overwrite: boolean = false
  ): Promise<DoctorScheduleItem[]> {
    const headers = await getAuthHeaders();
    const res = await fetch(
      `${API_BASE_URL}/api/v1/admin/doctors/${doctorId}/schedules/initialize-default?overwrite=${overwrite}`,
      {
        method: "POST",
        headers,
      }
    );
    return handleResponse<DoctorScheduleItem[]>(res);
  }

  /**
   * POST /api/v1/admin/doctors/repair-schedules
   * Identifies unscheduled doctors and initializes default schedules.
   */
  async repairSchedules(
    hospitalId?: string,
    dryRun: boolean = false
  ): Promise<{
    dry_run: boolean;
    unscheduled_count: number;
    repaired_count: number;
    doctors: Array<{ doctor_id: string; doctor_name: string; schedules_created?: number }>;
  }> {
    const headers = await getAuthHeaders();
    const query = new URLSearchParams();
    if (hospitalId) query.append("hospital_id", hospitalId);
    if (dryRun) query.append("dry_run", "true");
    const res = await fetch(
      `${API_BASE_URL}/api/v1/admin/doctors/repair-schedules?${query.toString()}`,
      {
        method: "POST",
        headers,
      }
    );
    return handleResponse<{
      dry_run: boolean;
      unscheduled_count: number;
      repaired_count: number;
      doctors: Array<{ doctor_id: string; doctor_name: string; schedules_created?: number }>;
    }>(res);
  }

  async getWorkload(): Promise<DoctorWorkload> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/doctors/me/workload`, {
      method: "GET",
      headers,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || "Failed to fetch doctor workload");
    }
    const data = await res.json();
    return {
      doctorId: data.doctor_id,
      doctorName: data.doctor_name,
      patientsCompletedToday: data.patients_completed_today,
      activeInRoomOrWaiting: data.active_in_room_or_waiting,
      meanConsultDurationMinutes: data.mean_consult_duration_minutes,
      clinicalUtilizationRate: data.clinical_utilization_rate,
      hourlyFlow: (data.hourly_flow || []).map((h: any) => ({
        hour: h.hour,
        count: h.count,
        avgMinutes: h.avg_minutes,
      })),
    };
  }
}

export const doctorService = new DoctorService();
