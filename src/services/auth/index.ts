import { User, UserRole, PatientProfile } from "@/types";

const MOCK_USERS: Record<UserRole, User> = {
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

const DEV_ROLE_TOKENS: Record<UserRole, string | undefined> = {
  patient:
    process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN ||
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJwYXRfMTAxIiwicm9sZSI6InBhdGllbnQiLCJhcHBfbWV0YWRhdGEiOnsicm9sZSI6InBhdGllbnQiLCJob3NwaXRhbF9pZCI6bnVsbH0sInVzZXJfbWV0YWRhdGEiOnsicm9sZSI6InBhdGllbnQiLCJob3NwaXRhbF9pZCI6bnVsbH0sImlhdCI6MTc5MDY1NTMzNywiZXhwIjoxODIyMTkxMzM3fQ.6UaZsRiqi82gF42VIyDXQ1Orc4ImluashU19Jy9sMwc",
  doctor:
    process.env.NEXT_PUBLIC_DEV_DOCTOR_AUTH_TOKEN ||
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkb2NfMjAyIiwicm9sZSI6ImRvY3RvciIsImFwcF9tZXRhZGF0YSI6eyJyb2xlIjoiZG9jdG9yIiwiaG9zcGl0YWxfaWQiOiJlMTRlMTQzNS1hZWNkLTQ4MGEtYWQxNC1lYWFlZDY3NTYwYmMifSwidXNlcl9tZXRhZGF0YSI6eyJyb2xlIjoiZG9jdG9yIiwiaG9zcGl0YWxfaWQiOiJlMTRlMTQzNS1hZWNkLTQ4MGEtYWQxNC1lYWFlZDY3NTYwYmMifSwiaWF0IjoxNzkyNjcwNjQ0LCJleHAiOjE4MjQyMDY2NDQsImhvc3BpdGFsX2lkIjoiZTE0ZTE0MzUtYWVjZC00ODBhLWFkMTQtZWFhZWQ2NzU2MGJjIn0._4cNE_VGNDwp3MAEM4RotdzRgR7wt8b71lK4gePBy5o",
  admin:
    process.env.NEXT_PUBLIC_DEV_ADMIN_AUTH_TOKEN ||
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1fMzAzIiwicm9sZSI6ImFkbWluIiwiYXBwX21ldGFkYXRhIjp7InJvbGUiOiJhZG1pbiIsImhvc3BpdGFsX2lkIjoiZTE0ZTE0MzUtYWVjZC00ODBhLWFkMTQtZWFhZWQ2NzU2MGJjIn0sInVzZXJfbWV0YWRhdGEiOnsicm9sZSI6ImFkbWluIiwiaG9zcGl0YWxfaWQiOiJlMTRlMTQzNS1hZWNkLTQ4MGEtYWQxNC1lYWFlZDY3NTYwYmMifSwiaWF0IjoxNzkyNjcwNjQ1LCJleHAiOjE4MjQyMDY2NDUsImhvc3BpdGFsX2lkIjoiZTE0ZTE0MzUtYWVjZC00ODBhLWFkMTQtZWFhZWQ2NzU2MGJjIn0.rcvzrL6a7cXo2IqOr8DD2K82imnnsZMR1jrDkIBoMk0",
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
          this.currentUser = MOCK_USERS.patient;
        }
      } else {
        // Default to patient for seamless preview
        this.currentUser = MOCK_USERS.patient;
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(this.currentUser));
      }

      if (this.currentUser) {
        const token = DEV_ROLE_TOKENS[this.currentUser.role];
        if (token && !localStorage.getItem("careroute_auth_token")) {
          localStorage.setItem("careroute_auth_token", token);
        }
      }
    } else {
      this.currentUser = MOCK_USERS.patient;
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

  loginAsRole(role: UserRole): User {
    const user = MOCK_USERS[role];
    this.currentUser = user;
    if (typeof window !== "undefined") {
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
      const token = DEV_ROLE_TOKENS[role];
      if (token) {
        localStorage.setItem("careroute_auth_token", token);
      }
    }
    return user;
  }

  logout(): void {
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

  getPatientProfile(): PatientProfile {
    return MOCK_PATIENT_PROFILE;
  }
}

export const authService = new AuthService();
