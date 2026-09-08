import { Appointment, AppointmentStatus } from "@/types";

let MOCK_APPOINTMENTS: Appointment[] = [
  {
    id: "apt_1001",
    patientId: "pat_101",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    doctorSpecialty: "Internal Medicine & Pulmonology",
    department: "Adult Outpatient Clinic",
    date: "Today",
    timeSlot: "11:30 AM",
    status: "scheduled",
    reasonForVisit: "Persistent dry cough and mild chest tight feeling for 4 days",
    triageUrgency: "routine",
    createdAt: new Date().toISOString(),
  },
  {
    id: "apt_1002",
    patientId: "pat_101",
    doctorId: "doc_204",
    doctorName: "Dr. Elena Rostova, MD",
    doctorSpecialty: "Orthopedics & Joint Health",
    department: "Musculoskeletal Wing",
    date: "Sep 22, 2026",
    timeSlot: "02:00 PM",
    status: "scheduled",
    reasonForVisit: "Follow-up knee assessment after physical therapy",
    triageUrgency: "routine",
    createdAt: new Date(Date.now() - 86400000 * 5).toISOString(),
  },
  {
    id: "apt_998",
    patientId: "pat_101",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    doctorSpecialty: "Internal Medicine",
    department: "Adult Outpatient Clinic",
    date: "Aug 14, 2026",
    timeSlot: "10:00 AM",
    status: "completed",
    reasonForVisit: "Annual preventive health exam",
    triageUrgency: "routine",
    createdAt: new Date(Date.now() - 86400000 * 25).toISOString(),
  },
];

const APPOINTMENTS_STORAGE_KEY = "careroute_appointments";

export class AppointmentService {
  private appointments: Appointment[] = [];

  constructor() {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(APPOINTMENTS_STORAGE_KEY);
      if (stored) {
        try {
          this.appointments = JSON.parse(stored);
        } catch {
          this.appointments = [...MOCK_APPOINTMENTS];
        }
      } else {
        this.appointments = [...MOCK_APPOINTMENTS];
        localStorage.setItem(APPOINTMENTS_STORAGE_KEY, JSON.stringify(this.appointments));
      }
    } else {
      this.appointments = [...MOCK_APPOINTMENTS];
    }
  }

  private persist() {
    if (typeof window !== "undefined") {
      localStorage.setItem(APPOINTMENTS_STORAGE_KEY, JSON.stringify(this.appointments));
    }
  }

  getAppointmentsByPatient(patientId: string): Appointment[] {
    return this.appointments.filter((a) => a.patientId === patientId);
  }

  getUpcomingAppointment(patientId: string): Appointment | undefined {
    return this.appointments.find(
      (a) =>
        a.patientId === patientId &&
        (a.status === "scheduled" || a.status === "checked_in")
    );
  }

  getAllAppointments(): Appointment[] {
    return this.appointments;
  }

  createAppointment(appointment: Omit<Appointment, "id" | "createdAt">): Appointment {
    const newAppointment: Appointment = {
      ...appointment,
      id: `apt_${Date.now()}`,
      createdAt: new Date().toISOString(),
    };
    this.appointments.unshift(newAppointment);
    this.persist();
    return newAppointment;
  }

  updateAppointmentStatus(id: string, status: AppointmentStatus): Appointment | undefined {
    const apt = this.appointments.find((a) => a.id === id);
    if (apt) {
      apt.status = status;
      this.persist();
    }
    return apt;
  }
}

export const appointmentService = new AppointmentService();
