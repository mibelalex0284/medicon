import { Consultation } from "@/types";

let ACTIVE_CONSULTATION: Consultation | null = {
  id: "c_901",
  queueEntryId: "q_001",
  patientId: "pat_801",
  patientName: "Robert Vance",
  doctorId: "doc_202",
  doctorName: "Dr. Anita Menon, MD",
  status: "active",
  startTime: new Date(Date.now() - 1000 * 60 * 8).toISOString(), // 8 minutes ago
  elapsedSeconds: 480,
  expectedDurationRange: { min: 12, max: 18 },
  clinicalNotes:
    "Patient presenting for routine hypertension review. Current BP measured at 138/86 mmHg. Reports mild morning lightheadedness with current Lisinopril 20mg dose.",
  diagnosis: "Essential hypertension, moderately controlled",
  prescriptions: ["Amlodipine 5mg (Oral Daily)", "Electrolyte Panel Order"],
  followUpRecommendation: "Return for clinic BP check in 6 weeks.",
};

export class ConsultationService {
  getActiveConsultation(doctorId: string): Consultation | null {
    return ACTIVE_CONSULTATION;
  }

  startNewConsultation(
    queueEntryId: string,
    patientId: string,
    patientName: string,
    doctorId: string,
    doctorName: string
  ): Consultation {
    ACTIVE_CONSULTATION = {
      id: `c_${Date.now()}`,
      queueEntryId,
      patientId,
      patientName,
      doctorId,
      doctorName,
      status: "active",
      startTime: new Date().toISOString(),
      elapsedSeconds: 0,
      expectedDurationRange: { min: 12, max: 18 },
      clinicalNotes: "",
      diagnosis: "",
      prescriptions: [],
    };
    return ACTIVE_CONSULTATION;
  }

  updateNotes(notes: string): void {
    if (ACTIVE_CONSULTATION) {
      ACTIVE_CONSULTATION.clinicalNotes = notes;
    }
  }

  updateDiagnosis(diagnosis: string): void {
    if (ACTIVE_CONSULTATION) {
      ACTIVE_CONSULTATION.diagnosis = diagnosis;
    }
  }

  addPrescription(rx: string): void {
    if (ACTIVE_CONSULTATION && rx.trim()) {
      ACTIVE_CONSULTATION.prescriptions.push(rx.trim());
    }
  }

  completeConsultation(): Consultation | null {
    if (ACTIVE_CONSULTATION) {
      ACTIVE_CONSULTATION.status = "completed";
      ACTIVE_CONSULTATION.endTime = new Date().toISOString();
      const completed = { ...ACTIVE_CONSULTATION };
      ACTIVE_CONSULTATION = null;
      return completed;
    }
    return null;
  }
}

export const consultationService = new ConsultationService();
