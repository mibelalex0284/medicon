import { User, UserRole, AuthoritativeRole, PatientProfile } from "../../types";
import { getSupabaseClient, isSupabaseConfigured } from "../../lib/supabase/client";

const MOCK_USERS: Record<AuthoritativeRole, User> = {
  patient: {
    id: "pat_101",
    email: "sarah.jenkins@example.com",
    name: "Sarah Jenkins",
    role: "patient",
    createdAt: "2026-01-15T09:00:00Z",
  },
  doctor: {
    id: "doc_202",
    email: "dr.menon@careroute.org",
    name: "Dr. Anita Menon, MD",
    role: "doctor",
    createdAt: "2025-06-10T08:30:00Z",
  },
  admin: {
    id: "adm_303",
    email: "ops.admin@careroute.org",
    name: "Mark Evans (Clinic Operations)",
    role: "admin",
    createdAt: "2025-01-01T08:00:00Z",
  },
};

const MOCK_PATIENT_PROFILE: PatientProfile = {
  id: "prof_101",
  userId: "pat_101",
  mrn: "CRX-9281",
  fullName: "Sarah Jenkins",
  dateOfBirth: "1988-04-12",
  gender: "Female",
  phone: "+1 (555) 349-8201",
  emergencyContact: {
    name: "David Jenkins",
    relationship: "Spouse",
    phone: "+1 (555) 349-8202",
  },
  bloodType: "A+",
  allergies: ["Penicillin", "Sulfa drugs"],
  medications: ["Lisinopril 10mg (Daily)", "Cetirizine 10mg (As needed)"],
  chronicConditions: ["Mild hypertension", "Seasonal allergic rhinitis"],
  preferredLanguage: "English",
  communicationPreference: "sms",
};

const AUTH_STORAGE_KEY = "careroute_user_session";

const DEV_ROLE_TOKENS: Record<AuthoritativeRole, string | undefined> = {
  patient: process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN,
  doctor: process.env.NEXT_PUBLIC_DEV_DOCTOR_AUTH_TOKEN,
  admin: process.env.NEXT_PUBLIC_DEV_ADMIN_AUTH_TOKEN,
};

export class AuthService {
  private currentUser: User | null = null;

  constructor() {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        try {
          this.currentUser = JSON.parse(stored);
        } catch {
          this.currentUser = null;
        }
      } else {
        // No auto-login: unauthenticated users remain null until explicitly authenticated
        this.currentUser = null;
      }
    }
  }

  getCurrentUser(): User | null {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        try {
          return JSON.parse(stored);
        } catch {
          return this.currentUser;
        }
      }
    }
    return this.currentUser;
  }

  async fetchAuthoritativeProfile(token: string): Promise<{
    role: UserRole;
    hasProfile: boolean;
    fullName?: string;
    email?: string;
    profileId?: string;
    hospitalId?: string | null;
  }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    let res: Response;
    try {
      res = await fetch(`${apiUrl}/api/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    } catch {
      throw new Error(
        "Network error: Unable to reach the authentication server to verify role permissions."
      );
    }

    if (res.status === 401) {
      throw new Error("AUTHENTICATION_EXPIRED");
    }

    if (!res.ok) {
      throw new Error(
        `Server error: Failed to verify account role with backend (status ${res.status}).`
      );
    }

    const me = await res.json();
    if (
      me.has_profile &&
      me.role &&
      ["patient", "doctor", "admin"].includes(String(me.role).toLowerCase())
    ) {
      return {
        role: String(me.role).toLowerCase() as UserRole,
        hasProfile: true,
        fullName: me.full_name,
        email: me.email,
        profileId: me.profile_id,
        hospitalId: me.hospital_id || null,
      };
    }

    // Authenticated Supabase identity without an application profile
    return {
      role: "unregistered",
      hasProfile: false,
      fullName: me.full_name,
      email: me.email,
      profileId: undefined,
      hospitalId: me.hospital_id || null,
    };
  }

  async restoreSession(): Promise<User | null> {
    if (typeof window === "undefined") return null;

    const supabase = getSupabaseClient();
    if (supabase && isSupabaseConfigured()) {
      try {
        const { data, error } = await supabase.auth.getSession();
        if (error || !data.session) {
          // Token expired or invalid
          await this.logout();
          return null;
        }

        const token = data.session.access_token;
        localStorage.setItem("careroute_auth_token", token);

        let authResult;
        try {
          authResult = await this.fetchAuthoritativeProfile(token);
        } catch (err: any) {
          if (err.message === "AUTHENTICATION_EXPIRED") {
            await this.logout();
            return null;
          }
          // Network or server error: do not silently grant a role or retain unverified session
          this.currentUser = null;
          localStorage.removeItem(AUTH_STORAGE_KEY);
          throw err;
        }

        const fullName =
          authResult.fullName ||
          data.session.user.user_metadata?.full_name ||
          data.session.user.email ||
          "User";

        const user: User = {
          id: data.session.user.id,
          email: data.session.user.email || "",
          name: fullName,
          role: authResult.role,
          createdAt: data.session.user.created_at,
          hospital_id: authResult.hospitalId || null,
        };

        this.currentUser = user;
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        return user;
      } catch (err: any) {
        if (err.message === "AUTHENTICATION_EXPIRED") {
          return null;
        }
        throw err;
      }
    }

    // In dev fallback mode, return current stored user if present
    return this.getCurrentUser();
  }

  async loginWithCredentials(email: string, password: string): Promise<User> {
    const supabase = getSupabaseClient();

    if (supabase && isSupabaseConfigured()) {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (error || !data.session) {
        throw new Error(error?.message || "Invalid email or password");
      }

      const token = data.session.access_token;
      if (typeof window !== "undefined") {
        localStorage.setItem("careroute_auth_token", token);
      }

      let authResult;
      try {
        authResult = await this.fetchAuthoritativeProfile(token);
      } catch (err: any) {
        this.currentUser = null;
        if (typeof window !== "undefined") {
          localStorage.removeItem(AUTH_STORAGE_KEY);
        }
        throw new Error(
          err.message || "Failed to resolve authenticated role permissions. Please try again."
        );
      }

      const fullName =
        authResult.fullName ||
        data.session.user.user_metadata?.full_name ||
        email;

      const user: User = {
        id: data.session.user.id,
        email: data.session.user.email || email,
        name: fullName,
        role: authResult.role,
        createdAt: data.session.user.created_at,
        hospital_id: authResult.hospitalId || null,
      };

      this.currentUser = user;
      if (typeof window !== "undefined") {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
      }
      return user;
    }

    // Fallback in development environments with unconfigured Supabase
    if (process.env.NODE_ENV === "development") {
      const normalizedEmail = email.toLowerCase().trim();
      let matchedRole: AuthoritativeRole | null = null;

      for (const [r, u] of Object.entries(MOCK_USERS)) {
        if (u.email.toLowerCase() === normalizedEmail) {
          matchedRole = r as AuthoritativeRole;
          break;
        }
      }

      if (!matchedRole) {
        throw new Error(
          "Supabase credentials are not configured. In development mode, sign in with one of the configured demo accounts: " +
            "sarah.jenkins@example.com (patient), dr.menon@careroute.org (doctor), or ops.admin@careroute.org (admin)."
        );
      }

      return this.loginAsRole(matchedRole);
    }

    throw new Error("Supabase authentication is not configured in this environment.");
  }

  loginAsRole(role: UserRole): User {
    if (process.env.NODE_ENV === "production") {
      throw new Error("Demo persona switching is strictly forbidden in production builds.");
    }

    if (role === "unregistered") {
      throw new Error("Cannot simulate unregistered persona directly.");
    }

    const user = MOCK_USERS[role as AuthoritativeRole];
    this.currentUser = user;
    if (typeof window !== "undefined") {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
      const token = DEV_ROLE_TOKENS[role as AuthoritativeRole];
      if (token) {
        localStorage.setItem("careroute_auth_token", token);
      }
    }
    return user;
  }

  async logout(): Promise<void> {
    const supabase = getSupabaseClient();
    if (supabase && isSupabaseConfigured()) {
      try {
        await supabase.auth.signOut();
      } catch {
        // Ignore sign-out network failures
      }
    }

    this.currentUser = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem("careroute_auth_token");
      sessionStorage.removeItem("careroute_auth_token");
      sessionStorage.removeItem("careroute_triage_session_id");
      sessionStorage.removeItem("careroute_triage_specialty_id");
      sessionStorage.removeItem("careroute_patient_concern");
    }
  }

  async getRegistrationStatus(): Promise<{ patient_self_registration_enabled: boolean }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const res = await fetch(`${apiUrl}/api/v1/auth/registration-status`);
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // In development fallback if backend is unreachable
    }
    return { patient_self_registration_enabled: true };
  }

  async registerPatient(payload: {
    full_name: string;
    email: string;
    password: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }): Promise<User> {
    const status = await this.getRegistrationStatus();
    if (!status.patient_self_registration_enabled) {
      throw new Error(
        "Public patient registration is currently disabled by clinic administration."
      );
    }

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const supabase = getSupabaseClient();

    if (supabase && isSupabaseConfigured()) {
      const { data, error } = await supabase.auth.signUp({
        email: payload.email,
        password: payload.password,
        options: {
          data: {
            full_name: payload.full_name,
            role: "patient",
          },
        },
      });

      if (error) {
        throw new Error(error.message || "Failed to create authentication account");
      }

      const token = data.session?.access_token;
      if (token) {
        if (typeof window !== "undefined") {
          localStorage.setItem("careroute_auth_token", token);
        }

        const profileRes = await fetch(`${apiUrl}/api/v1/auth/complete-patient-profile`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            full_name: payload.full_name,
            email: payload.email,
            date_of_birth: payload.date_of_birth,
            phone: payload.phone || null,
            emergency_contact: payload.emergency_contact || null,
            preferred_language: payload.preferred_language || "en",
          }),
        });

        if (!profileRes.ok) {
          const errData = await profileRes.json().catch(() => ({}));
          throw new Error(
            errData.detail || errData.message || "Failed to complete patient profile record"
          );
        }

        const user: User = {
          id: data.user?.id || `pat_${Date.now()}`,
          email: payload.email,
          name: payload.full_name,
          role: "patient",
          createdAt: new Date().toISOString(),
        };

        this.currentUser = user;
        if (typeof window !== "undefined") {
          localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        }
        return user;
      } else {
        const user: User = {
          id: data.user?.id || `pat_${Date.now()}`,
          email: payload.email,
          name: payload.full_name,
          role: "patient",
          createdAt: new Date().toISOString(),
        };
        return user;
      }
    }

    if (process.env.NODE_ENV === "development") {
      const user: User = {
        id: `pat_${Date.now()}`,
        email: payload.email,
        name: payload.full_name,
        role: "patient",
        createdAt: new Date().toISOString(),
      };
      this.currentUser = user;
      if (typeof window !== "undefined") {
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        const token = DEV_ROLE_TOKENS.patient;
        if (token) {
          localStorage.setItem("careroute_auth_token", token);
        }
      }
      return user;
    }

    throw new Error("Supabase authentication is not configured in this environment.");
  }

  async completePatientProfile(payload: {
    full_name: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }): Promise<User> {
    const status = await this.getRegistrationStatus();
    if (!status.patient_self_registration_enabled) {
      throw new Error(
        "Public patient registration is currently disabled by clinic administration."
      );
    }

    const token = typeof window !== "undefined" ? localStorage.getItem("careroute_auth_token") : null;
    if (!token) {
      throw new Error("Authentication token missing. Please sign in again.");
    }
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const res = await fetch(`${apiUrl}/api/v1/auth/complete-patient-profile`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        full_name: payload.full_name,
        date_of_birth: payload.date_of_birth,
        phone: payload.phone || null,
        emergency_contact: payload.emergency_contact || null,
        preferred_language: payload.preferred_language || "en",
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const code = err.code || err.error?.code;
      if (code === "REGISTRATION_DISABLED") {
        throw new Error("Public patient registration is currently disabled by clinic administration.");
      }
      throw new Error(err.message || err.detail || "Failed to complete patient profile");
    }

    return (await this.restoreSession()) || {
      id: this.currentUser?.id || `pat_${Date.now()}`,
      email: this.currentUser?.email || "",
      name: payload.full_name,
      role: "patient",
      createdAt: new Date().toISOString(),
    };
  }

  async getAdminSettings(): Promise<{
    patient_self_registration_enabled: boolean;
    settings: Array<{ key: string; value: string; description?: string | null; updated_at?: string | null; updated_by?: string | null }>;
  }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = typeof window !== "undefined" ? localStorage.getItem("careroute_auth_token") : null;
    const res = await fetch(`${apiUrl}/api/v1/admin/settings`, {
      headers: {
        Authorization: `Bearer ${token || ""}`,
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || "Failed to load admin settings");
    }
    return res.json();
  }

  async updatePatientSelfRegistration(enabled: boolean): Promise<{
    patient_self_registration_enabled: boolean;
    settings: Array<{ key: string; value: string; description?: string | null; updated_at?: string | null; updated_by?: string | null }>;
  }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = typeof window !== "undefined" ? localStorage.getItem("careroute_auth_token") : null;
    const res = await fetch(`${apiUrl}/api/v1/admin/settings/patient-self-registration`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token || ""}`,
      },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || "Failed to update registration setting");
    }
    return res.json();
  }

  async adminRegisterPatient(payload: {
    full_name: string;
    email: string;
    date_of_birth: string;
    phone?: string | null;
    emergency_contact?: string | null;
    preferred_language?: string;
    hospital_id?: string | null;
  }): Promise<{
    status: string;
    profile_id: string;
    auth_user_id: string;
    role: string;
    full_name: string;
    email: string;
    entity_id: string;
    auth_provisioned: boolean;
    message: string;
  }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = typeof window !== "undefined" ? localStorage.getItem("careroute_auth_token") : null;
    const res = await fetch(`${apiUrl}/api/v1/admin/patients/register`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token || ""}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || "Failed to register patient account");
    }
    return res.json();
  }

  async adminOnboardDoctor(payload: {
    full_name: string;
    email: string;
    license_number: string;
    hospital_id: string;
    department_id?: string | null;
    specialty_ids?: string[];
    primary_specialty_id?: string | null;
    years_of_experience?: number;
    consultation_mode?: string;
    languages?: string;
    phone?: string | null;
  }): Promise<{
    status: string;
    profile_id: string;
    auth_user_id: string;
    role: string;
    full_name: string;
    email: string;
    entity_id: string;
    auth_provisioned: boolean;
    message: string;
    invitation_sent?: boolean;
    action_link?: string | null;
  }> {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const token = typeof window !== "undefined" ? localStorage.getItem("careroute_auth_token") : null;
    const res = await fetch(`${apiUrl}/api/v1/admin/doctors/onboard`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token || ""}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || "Failed to onboard physician");
    }
    return res.json();
  }

  getPatientProfile(): PatientProfile {
    return MOCK_PATIENT_PROFILE;
  }
}


export const authService = new AuthService();


