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
    }
    return user;
  }

  logout(): void {
    this.currentUser = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  }

  getPatientProfile(): PatientProfile {
    return MOCK_PATIENT_PROFILE;
  }
}

export const authService = new AuthService();
