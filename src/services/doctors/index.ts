import { getSupabaseClient } from "@/lib/supabase/client";
import { Doctor } from "@/types";

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
    // 1. Explicit token in localStorage / sessionStorage
    const storedToken =
      localStorage.getItem("careroute_auth_token") ||
      sessionStorage.getItem("careroute_auth_token");
    if (storedToken) {
      headers["Authorization"] = `Bearer ${storedToken}`;
      return headers;
    }

    // 2. Supabase auth token
    try {
      const supabase = getSupabaseClient();
      if (supabase) {
        const { data } = await supabase.auth.getSession();
        if (data?.session?.access_token) {
          headers["Authorization"] = `Bearer ${data.session.access_token}`;
          return headers;
        }
      }
    } catch {
      // Supabase not configured or in fallback mode
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

// Retained static mock database for non-recommendation fallback/preview
export const DOCTORS_DATABASE: Doctor[] = [
  {
    id: "doc_202",
    userId: "doc_202",
    name: "Dr. Anita Menon, MD",
    title: "Senior Consultant",
    specialty: "Internal Medicine & Pulmonology",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    languages: ["English", "Hindi", "Malayalam"],
    experienceYears: 14,
    education: "Johns Hopkins School of Medicine",
    currentWaitRange: { min: 20, max: 35 },
    activeQueueCount: 4,
    isAvailable: true,
  },
  {
    id: "doc_203",
    userId: "doc_203",
    name: "Dr. Marcus Chen, MD",
    title: "Attending Physician",
    specialty: "Cardiology & Vascular Medicine",
    department: "Cardiovascular Pavilion",
    roomNumber: "Room 112",
    languages: ["English", "Mandarin"],
    experienceYears: 11,
    education: "Stanford University Medical Center",
    currentWaitRange: { min: 35, max: 50 },
    activeQueueCount: 6,
    isAvailable: true,
  },
  {
    id: "doc_204",
    userId: "doc_204",
    name: "Dr. Elena Rostova, MD",
    title: "Consultant Orthopedic Specialist",
    specialty: "Orthopedics & Joint Health",
    department: "Musculoskeletal Wing",
    roomNumber: "Room 305",
    languages: ["English", "Russian"],
    experienceYears: 16,
    education: "Mayo Clinic Alix School of Medicine",
    currentWaitRange: { min: 15, max: 25 },
    activeQueueCount: 2,
    isAvailable: true,
  },
  {
    id: "doc_205",
    userId: "doc_205",
    name: "Dr. Tariq Al-Mansoor, MD",
    title: "Staff Physician",
    specialty: "Gastroenterology & Hepatology",
    department: "Digestive Disease Suite",
    roomNumber: "Room 218",
    languages: ["English", "Arabic"],
    experienceYears: 9,
    education: "Columbia University Vagelos College of P&S",
    currentWaitRange: { min: 30, max: 45 },
    activeQueueCount: 5,
    isAvailable: true,
  },
  {
    id: "doc_206",
    userId: "doc_206",
    name: "Dr. Sarah Lindqvist, MD",
    title: "Pediatric Specialist",
    specialty: "Pediatrics & Adolescent Medicine",
    department: "Children's Health Pavilion",
    roomNumber: "Room 101",
    languages: ["English", "Swedish"],
    experienceYears: 12,
    education: "Karolinska Institutet & Boston Children's",
    currentWaitRange: { min: 10, max: 20 },
    activeQueueCount: 3,
    isAvailable: true,
  },
];

export interface DoctorLifecycleResponse {
  doctor_id: string;
  profile_id: string;
  full_name: string;
  email: string;
  is_active: boolean;
  status: "active" | "deactivated" | "deleted";
  message: string;
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

  getAllDoctors(): Doctor[] {
    return DOCTORS_DATABASE;
  }

  getDoctorById(id: string): Doctor | undefined {
    return DOCTORS_DATABASE.find((d) => d.id === id);
  }

  getExplainableMatches(
    recommendedSpecialties: string[] = ["Internal Medicine"],
    preferredLanguage: string = "English"
  ): { recommendedDoctor: Doctor; alternativeDoctors: Doctor[] } {
    const scored = DOCTORS_DATABASE.map((doc) => {
      let score = 50;
      const matchReasons: string[] = [];

      const matchesSpecialty = recommendedSpecialties.some((spec) =>
        doc.specialty.toLowerCase().includes(spec.toLowerCase())
      );
      if (matchesSpecialty) {
        score += 35;
        matchReasons.push(`Direct specialty alignment for ${doc.specialty}`);
      } else {
        matchReasons.push("General outpatient medical expertise");
      }

      if (doc.activeQueueCount <= 4) {
        score += 15;
        matchReasons.push(`Low queue load (${doc.activeQueueCount} patients currently ahead)`);
      } else {
        matchReasons.push(`Moderate clinic volume (${doc.activeQueueCount} patients in queue)`);
      }

      if (doc.languages.includes(preferredLanguage)) {
        score += 10;
        matchReasons.push(`Fluent in your preferred language (${preferredLanguage})`);
      }

      if (doc.currentWaitRange.min <= 20) {
        score += 10;
        matchReasons.push(`Estimated wait of ${doc.currentWaitRange.min}–${doc.currentWaitRange.max} min`);
      }

      return {
        ...doc,
        matchScore: score,
        matchReasons,
      };
    }).sort((a, b) => (b.matchScore || 0) - (a.matchScore || 0));

    return {
      recommendedDoctor: scored[0],
      alternativeDoctors: scored.slice(1),
    };
  }
}

export const doctorService = new DoctorService();
