export type AuthoritativeRole = "patient" | "doctor" | "admin";
export type UserRole = AuthoritativeRole | "unregistered";

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  avatarUrl?: string;
  createdAt: string;
  hospital_id?: string | null;
}

export interface PatientProfile {
  id: string;
  userId: string;
  mrn: string; // Medical Record Number
  fullName: string;
  dateOfBirth: string;
  gender: string;
  phone: string;
  emergencyContact: {
    name: string;
    relationship: string;
    phone: string;
  };
  bloodType?: string;
  allergies: string[];
  medications: string[];
  chronicConditions: string[];
  preferredLanguage: string;
  communicationPreference: "sms" | "whatsapp" | "email";
}

export interface Doctor {
  id: string;
  userId: string;
  name: string;
  title: string;
  specialty: string;
  department: string;
  roomNumber: string;
  languages: string[];
  avatarUrl?: string;
  experienceYears: number;
  education: string;
  currentWaitRange: {
    min: number;
    max: number;
  };
  activeQueueCount: number;
  isAvailable: boolean;
  matchScore?: number;
  matchReasons?: string[];
}

export type TriageUrgency = "emergency" | "urgent" | "routine" | "self_care";

export interface RedFlagAlert {
  isTriggered: boolean;
  title: string;
  message: string;
  actionRecommendation: string;
  hotline?: string;
}

export interface TriageQuestion {
  id: string;
  title: string;
  explanation?: string;
  options: {
    id: string;
    label: string;
    description?: string;
    isRedFlag?: boolean;
  }[];
  multiSelect?: boolean;
}

export interface TriageSession {
  id: string;
  patientId: string;
  chiefComplaint: string;
  duration: string;
  severity: "mild" | "moderate" | "severe";
  answers: Record<string, string[]>;
  redFlagAlert?: RedFlagAlert;
  urgency: TriageUrgency;
  recommendedSpecialties: string[];
  careDirection: string;
  confirmedFacts: string[];
  completedAt?: string;
}

export type AppointmentStatus =
  | "scheduled"
  | "checked_in"
  | "in_consultation"
  | "completed"
  | "cancelled"
  | "no_show";

export interface Appointment {
  id: string;
  patientId: string;
  patientName?: string;
  doctorId: string;
  doctorName: string;
  doctorSpecialty: string;
  department: string;
  date: string;
  timeSlot: string;
  status: AppointmentStatus;
  reasonForVisit: string;
  triageUrgency?: TriageUrgency;
  queueToken?: string;
  queueEntryId?: string;
  hospitalId?: string;
  scheduledStart?: string;
  scheduledEnd?: string;
  appointmentDate?: string;
  rawStatus?: string;
  createdAt: string;
}

export type QueueStatus =
  | "waiting"
  | "called"
  | "in_consultation"
  | "completed"
  | "no_show";

export interface QueueEntry {
  id: string;
  token: string; // e.g., "A24"
  patientId: string;
  patientName: string;
  patientAge?: number;
  patientGender?: string;
  doctorId: string;
  doctorName: string;
  department: string;
  roomNumber: string;
  appointmentId?: string;
  status: QueueStatus;
  positionAhead: number;
  estimatedWaitMinutes: {
    min: number;
    max: number;
  };
  triageUrgency: TriageUrgency;
  chiefComplaint: string;
  checkInTime: string;
  calledTime?: string;
  consultationStartTime?: string;
  consultationEndTime?: string;
  updatedAt: string;
}

export interface Consultation {
  id: string;
  queueEntryId: string;
  appointmentId?: string;
  patientId: string;
  patientName: string;
  doctorId: string;
  doctorName: string;
  status: "active" | "completed";
  startTime: string;
  endTime?: string;
  elapsedSeconds: number;
  expectedDurationRange: {
    min: number;
    max: number;
  };
  clinicalNotes: string;
  diagnosis: string;
  prescriptions: string[];
  followUpRecommendation?: string;
  triageSessionId?: string;
  intakeSummary?: {
    chiefComplaint: string;
    duration?: string;
    severity?: number;
    urgency?: string;
    specialty?: string;
    presentSymptoms?: string[];
    absentSymptoms?: string[];
    unknownSymptoms?: string[];
    safetyScreenings?: Record<string, string>;
    conversationSummary?: string;
  };
}

export interface HealthArticle {
  id: string;
  slug: string;
  title: string;
  summary: string;
  category: string;
  content: string[];
  sourceName: string;
  sourceUrl: string;
  citation: string;
  freshnessDate: string;
  reviewedBy: string;
}

export interface DepartmentStats {
  id: string;
  name: string;
  activeDoctors: number;
  totalWaiting: number;
  meanWaitMinutes: number;
  p90WaitMinutes: number;
  urgentCasesCount: number;
  currentBottleneck?: string;
}

export interface ClinicAnalytics {
  totalPatientsToday: number;
  activeQueueCount: number;
  inConsultationCount: number;
  completedToday: number;
  meanWaitMinutes: number;
  p90WaitMinutes: number;
  urgentDelayRate: number; // percentage e.g. 4.2%
  doctorUtilizationRate: number; // percentage e.g. 88%
  punctualityRate: number; // percentage e.g. 92%
}

export interface HourlyThroughput {
  hour: string;
  arrivals: number;
  completed: number;
}

export interface DoctorHourlySlot {
  hour: string;
  count: number;
  avgMinutes: number;
}

export interface DoctorWorkload {
  doctorId: string;
  doctorName: string;
  patientsCompletedToday: number;
  activeInRoomOrWaiting: number;
  meanConsultDurationMinutes: number;
  clinicalUtilizationRate: number;
  hourlyFlow: DoctorHourlySlot[];
}

