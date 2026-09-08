import { Doctor } from "@/types";

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

export class DoctorService {
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

      // Factor 1: Clinical specialty alignment
      const matchesSpecialty = recommendedSpecialties.some((spec) =>
        doc.specialty.toLowerCase().includes(spec.toLowerCase())
      );
      if (matchesSpecialty) {
        score += 35;
        matchReasons.push(`Direct specialty alignment for ${doc.specialty}`);
      } else {
        matchReasons.push("General outpatient medical expertise");
      }

      // Factor 2: Queue load & availability
      if (doc.activeQueueCount <= 4) {
        score += 15;
        matchReasons.push(`Low queue load (${doc.activeQueueCount} patients currently ahead)`);
      } else {
        matchReasons.push(`Moderate clinic volume (${doc.activeQueueCount} patients in queue)`);
      }

      // Factor 3: Language proficiency
      if (doc.languages.includes(preferredLanguage)) {
        score += 10;
        matchReasons.push(`Fluent in your preferred language (${preferredLanguage})`);
      }

      // Factor 4: Shorter estimated wait
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
