import { TriageQuestion, TriageSession, RedFlagAlert, TriageUrgency } from "@/types";

export const CLINICAL_TRIAGE_QUESTIONS: TriageQuestion[] = [
  {
    id: "primary_symptom",
    title: "What is your primary physical concern or symptom?",
    explanation: "Select the option that best describes what is troubling you today.",
    options: [
      { id: "chest_discomfort", label: "Chest pressure or discomfort", isRedFlag: true },
      { id: "respiratory_cough", label: "Cough, shortness of breath, or wheezing" },
      { id: "abdominal_pain", label: "Stomach pain, nausea, or digestive issues" },
      { id: "joint_muscle", label: "Joint, bone, or muscular aches" },
      { id: "headache_fever", label: "Headache, dizziness, or fever" },
      { id: "skin_rash", label: "Skin rash, itch, or unusual lesion" },
    ],
  },
  {
    id: "symptom_duration",
    title: "How long have you been experiencing these symptoms?",
    explanation: "This helps determine whether this is an acute episode or a persistent concern.",
    options: [
      { id: "under_24h", label: "Less than 24 hours (Sudden onset)" },
      { id: "1_to_3_days", label: "1 to 3 days" },
      { id: "1_to_2_weeks", label: "1 to 2 weeks" },
      { id: "over_2_weeks", label: "More than 2 weeks (Persistent)" },
    ],
  },
  {
    id: "severity_impact",
    title: "How significantly does this affect your daily activities?",
    explanation: "Rate the functional impact of your current discomfort.",
    options: [
      { id: "mild", label: "Mild — Noticeable, but able to work and sleep normally" },
      { id: "moderate", label: "Moderate — Limits physical activity or disrupts sleep" },
      { id: "severe", label: "Severe — Incapacitating, unable to perform basic tasks" },
    ],
  },
  {
    id: "associated_red_flags",
    title: "Are you experiencing any of the following critical warning signs?",
    explanation: "Please read carefully. These indicators require prompt emergency medical attention.",
    options: [
      { id: "crushing_chest_pain", label: "Radiating chest pain to left arm or jaw with cold sweats", isRedFlag: true },
      { id: "acute_breath_shortness", label: "Sudden severe difficulty breathing while resting", isRedFlag: true },
      { id: "facial_droop_slur", label: "Sudden facial drooping, arm weakness, or slurred speech", isRedFlag: true },
      { id: "blood_cough_vomit", label: "Coughing up blood or dark vomiting", isRedFlag: true },
      { id: "none_of_above", label: "None of these critical warning signs" },
    ],
    multiSelect: true,
  },
];

export class TriageService {
  evaluateTriageAnswers(
    chiefComplaint: string,
    answers: Record<string, string[]>
  ): {
    urgency: TriageUrgency;
    redFlagAlert?: RedFlagAlert;
    careDirection: string;
    recommendedSpecialties: string[];
    confirmedFacts: string[];
  } {
    const primary = answers["primary_symptom"]?.[0] || "";
    const duration = answers["symptom_duration"]?.[0] || "";
    const severity = answers["severity_impact"]?.[0] || "";
    const flags = answers["associated_red_flags"] || [];

    const hasRedFlagTrigger =
      primary === "chest_discomfort" ||
      flags.some((f) =>
        [
          "crushing_chest_pain",
          "acute_breath_shortness",
          "facial_droop_slur",
          "blood_cough_vomit",
        ].includes(f)
      );

    if (hasRedFlagTrigger) {
      return {
        urgency: "emergency",
        redFlagAlert: {
          isTriggered: true,
          title: "Critical Warning Signs Detected",
          message:
            "Your reported symptoms suggest a potentially acute cardiovascular, neurological, or respiratory event that requires immediate emergency evaluation rather than routine outpatient queuing.",
          actionRecommendation:
            "Proceed immediately to the nearest Emergency Department or dial 911. Do not drive yourself.",
          hotline: "911 / (800) 555-ER-TRIAGE",
        },
        careDirection: "Immediate Emergency Department Escalation",
        recommendedSpecialties: ["Emergency Medicine", "Interventional Cardiology"],
        confirmedFacts: [
          `Reported concern: "${chiefComplaint || "Acute symptoms"}"`,
          "Critical red flag alert triggered based on clinical intake safety guidelines",
          "Outpatient clinic queue bypassed for patient safety",
        ],
      };
    }

    if (severity === "severe" || duration === "under_24h") {
      return {
        urgency: "urgent",
        careDirection: "Same-Day Urgent Care or Priority Outpatient Evaluation",
        recommendedSpecialties:
          primary === "respiratory_cough"
            ? ["Pulmonology", "Internal Medicine"]
            : primary === "abdominal_pain"
            ? ["Gastroenterology", "General Surgery"]
            : ["Internal Medicine"],
        confirmedFacts: [
          `Chief concern: "${chiefComplaint || "Acute concern"}"`,
          "Symptoms reported as moderate to severe or acute onset",
          "Expedited outpatient queue assigned",
        ],
      };
    }

    // Routine outpatient
    let specialties = ["Internal Medicine", "General Practice"];
    if (primary === "joint_muscle") specialties = ["Orthopedics", "Physical Medicine"];
    if (primary === "skin_rash") specialties = ["Dermatology", "Allergy & Immunology"];
    if (primary === "respiratory_cough") specialties = ["Pulmonology", "General Medicine"];

    return {
      urgency: "routine",
      careDirection: "Standard Outpatient Consultation & Doctor Matching",
      recommendedSpecialties: specialties,
      confirmedFacts: [
        `Chief concern: "${chiefComplaint || "Outpatient concern"}"`,
        `Duration: ${duration.replace(/_/g, " ")}`,
        `Functional impact: ${severity}`,
        "No acute emergency indicators identified",
      ],
    };
  }
}

export const triageService = new TriageService();
