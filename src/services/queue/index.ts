import { QueueEntry, QueueStatus } from "@/types";

let INITIAL_QUEUE_ENTRIES: QueueEntry[] = [
  {
    id: "q_001",
    token: "A21",
    patientId: "pat_801",
    patientName: "Robert Vance",
    patientAge: 54,
    patientGender: "Male",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    status: "in_consultation",
    positionAhead: 0,
    estimatedWaitMinutes: { min: 0, max: 0 },
    triageUrgency: "routine",
    chiefComplaint: "Hypertension medication review & blood pressure check",
    checkInTime: "10:45 AM",
    consultationStartTime: "11:05 AM",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "q_002",
    token: "A22",
    patientId: "pat_802",
    patientName: "Emily Wong",
    patientAge: 32,
    patientGender: "Female",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    status: "called",
    positionAhead: 0,
    estimatedWaitMinutes: { min: 0, max: 5 },
    triageUrgency: "urgent",
    chiefComplaint: "Acute asthma flare with wheezing on exertion",
    checkInTime: "11:00 AM",
    calledTime: "11:15 AM",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "q_003",
    token: "A23",
    patientId: "pat_803",
    patientName: "Carlos Ramirez",
    patientAge: 46,
    patientGender: "Male",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    status: "waiting",
    positionAhead: 1,
    estimatedWaitMinutes: { min: 10, max: 20 },
    triageUrgency: "routine",
    chiefComplaint: "Subacute sinus pressure and fever for 3 days",
    checkInTime: "11:05 AM",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "q_004",
    token: "A24",
    patientId: "pat_101", // Current demo patient: Sarah Jenkins
    patientName: "Sarah Jenkins",
    patientAge: 38,
    patientGender: "Female",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    status: "waiting",
    positionAhead: 2,
    estimatedWaitMinutes: { min: 25, max: 35 },
    triageUrgency: "routine",
    chiefComplaint: "Persistent dry cough and chest tightness for 4 days",
    checkInTime: "11:10 AM",
    updatedAt: new Date().toISOString(),
  },
  {
    id: "q_005",
    token: "A25",
    patientId: "pat_805",
    patientName: "Aiden Miller",
    patientAge: 29,
    patientGender: "Male",
    doctorId: "doc_202",
    doctorName: "Dr. Anita Menon, MD",
    department: "Adult Outpatient Clinic",
    roomNumber: "Room 204",
    status: "waiting",
    positionAhead: 3,
    estimatedWaitMinutes: { min: 40, max: 55 },
    triageUrgency: "routine",
    chiefComplaint: "Post-viral fatigue and mild dizziness",
    checkInTime: "11:18 AM",
    updatedAt: new Date().toISOString(),
  },
];

const QUEUE_STORAGE_KEY = "careroute_queue_entries";
type QueueListener = (entries: QueueEntry[]) => void;

export class QueueService {
  private queue: QueueEntry[] = [];
  private listeners: Set<QueueListener> = new Set();

  constructor() {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(QUEUE_STORAGE_KEY);
      if (stored) {
        try {
          this.queue = JSON.parse(stored);
        } catch {
          this.queue = [...INITIAL_QUEUE_ENTRIES];
        }
      } else {
        this.queue = [...INITIAL_QUEUE_ENTRIES];
        localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(this.queue));
      }
    } else {
      this.queue = [...INITIAL_QUEUE_ENTRIES];
    }
  }

  private persistAndNotify() {
    this.recalculatePositionsAndEstimates();
    if (typeof window !== "undefined") {
      localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(this.queue));
    }
    this.listeners.forEach((listener) => listener([...this.queue]));
  }

  private recalculatePositionsAndEstimates() {
    // Only waiting or called patients in active queue
    const activeWaiting = this.queue.filter(
      (q) => q.status === "waiting" || q.status === "called"
    );

    activeWaiting.forEach((entry, index) => {
      if (entry.status === "called") {
        entry.positionAhead = 0;
        entry.estimatedWaitMinutes = { min: 0, max: 5 };
      } else {
        entry.positionAhead = index;
        // Uncertainty model: 12-18 minutes per consultation variance
        const minTime = Math.max(5, index * 10);
        const maxTime = Math.max(10, index * 18 + 5);
        entry.estimatedWaitMinutes = { min: minTime, max: maxTime };
      }
      entry.updatedAt = new Date().toISOString();
    });
  }

  subscribe(listener: QueueListener): () => void {
    this.listeners.add(listener);
    listener([...this.queue]);
    return () => {
      this.listeners.delete(listener);
    };
  }

  getAllQueue(): QueueEntry[] {
    return [...this.queue];
  }

  getDoctorQueue(doctorId: string): QueueEntry[] {
    return this.queue.filter(
      (q) => q.doctorId === doctorId && q.status !== "completed"
    );
  }

  getPatientActiveQueue(patientId: string): QueueEntry | undefined {
    return this.queue.find(
      (q) =>
        q.patientId === patientId &&
        ["waiting", "called", "in_consultation"].includes(q.status)
    );
  }

  checkInPatient(
    patientId: string,
    patientName: string,
    doctorId: string,
    doctorName: string,
    chiefComplaint: string,
    urgency: "routine" | "urgent" | "emergency"
  ): QueueEntry {
    // Check if already in queue
    const existing = this.getPatientActiveQueue(patientId);
    if (existing) return existing;

    const tokenNumber = this.queue.length + 21;
    const token = `A${tokenNumber}`;

    const newEntry: QueueEntry = {
      id: `q_${Date.now()}`,
      token,
      patientId,
      patientName,
      doctorId,
      doctorName,
      department: "Adult Outpatient Clinic",
      roomNumber: "Room 204",
      status: "waiting",
      positionAhead: this.queue.filter((q) => q.status === "waiting").length,
      estimatedWaitMinutes: { min: 25, max: 35 },
      triageUrgency: urgency,
      chiefComplaint,
      checkInTime: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      updatedAt: new Date().toISOString(),
    };

    this.queue.push(newEntry);
    this.persistAndNotify();
    return newEntry;
  }

  callPatient(queueId: string): QueueEntry | undefined {
    const entry = this.queue.find((q) => q.id === queueId);
    if (entry) {
      entry.status = "called";
      entry.calledTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      this.persistAndNotify();
    }
    return entry;
  }

  startConsultation(queueId: string): QueueEntry | undefined {
    const entry = this.queue.find((q) => q.id === queueId);
    if (entry) {
      entry.status = "in_consultation";
      entry.consultationStartTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      this.persistAndNotify();
    }
    return entry;
  }

  completeConsultation(queueId: string): QueueEntry | undefined {
    const entry = this.queue.find((q) => q.id === queueId);
    if (entry) {
      entry.status = "completed";
      entry.consultationEndTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
      this.persistAndNotify();
    }
    return entry;
  }

  markNoShow(queueId: string): QueueEntry | undefined {
    const entry = this.queue.find((q) => q.id === queueId);
    if (entry) {
      entry.status = "no_show";
      this.persistAndNotify();
    }
    return entry;
  }
}

export const queueService = new QueueService();
