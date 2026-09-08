import { HealthArticle } from "@/types";

export const HEALTH_ARTICLES: HealthArticle[] = [
  {
    id: "art_101",
    slug: "managing-acute-cough-guidelines",
    title: "Understanding Acute Cough: Viral vs. Bacterial Indicators",
    summary:
      "A clinical review of common triggers for acute cough, normal recovery timelines (up to 3 weeks), and when secondary bacterial infection should be considered by a clinician.",
    category: "Respiratory Health",
    content: [
      "Most acute coughs lasting under three weeks are precipitated by common viral respiratory tract infections. Antibiotics are ineffective against viral etiologies.",
      "Hydration, humidified air, and elevation during rest can alleviate symptom burden without pharmacological risks.",
      "Red-flag warning signs requiring urgent clinical evaluation include hemoptysis (coughing up blood), sustained high fevers above 102°F, shortness of breath at rest, or pleuritic chest pain.",
    ],
    sourceName: "American College of Chest Physicians (CHEST)",
    sourceUrl: "https://www.chestnet.org",
    citation: "Irwin RS, et al. Classification of Cough as a Symptom in Adults and Management Guidelines. CHEST 2018; 153(1):196-209.",
    freshnessDate: "Reviewed January 2026",
    reviewedBy: "Dr. Anita Menon, MD (Internal Medicine)",
  },
  {
    id: "art_102",
    slug: "blood-pressure-monitoring-home-guide",
    title: "Accurate Home Blood Pressure Monitoring: Clinical Best Practices",
    summary:
      "Step-by-step guidance on positioning, cuff sizing, and timing for reliable self-measured blood pressure readings to share with your physician.",
    category: "Cardiovascular Wellness",
    content: [
      "Rest quietly for 5 minutes in a comfortable chair with back supported and feet flat on the floor before initiating measurement.",
      "Ensure the cuff is positioned at heart level. Avoid caffeine, exercise, and tobacco for 30 minutes prior to reading.",
      "Take two readings 1 minute apart morning and evening for one week ahead of your scheduled clinical follow-up.",
    ],
    sourceName: "American Heart Association (AHA / ACC)",
    sourceUrl: "https://www.heart.org",
    citation: "Whelton PK, et al. ACC/AHA High Blood Pressure Clinical Practice Guideline. Circulation 2018; 138:e484–e594.",
    freshnessDate: "Updated December 2025",
    reviewedBy: "Dr. Marcus Chen, MD (Cardiology)",
  },
  {
    id: "art_103",
    slug: "knee-joint-pain-ergonomics-rehab",
    title: "Post-Activity Knee Joint Discomfort: Conservative Management Protocols",
    summary:
      "Evidence-backed conservative strategies for managing mild anterior knee soreness, quadriceps strengthening, and patellar tracking ergonomics.",
    category: "Musculoskeletal & Orthopedics",
    content: [
      "Targeted quad activation (isometric straight leg raises) strengthens the stabilizing musculature around the patella.",
      "Avoid deep loaded flexion past 90 degrees while acute inflammation is present.",
      "If joint effusion (swelling), inability to bear weight, or a locking sensation occurs, immediate physical orthopedic evaluation is indicated.",
    ],
    sourceName: "American Academy of Orthopaedic Surgeons (AAOS)",
    sourceUrl: "https://www.aaos.org",
    citation: "AAOS Clinical Practice Guideline on the Treatment of Osteoarthritis of the Knee (3rd Edition). JAAOS 2022.",
    freshnessDate: "Reviewed November 2025",
    reviewedBy: "Dr. Elena Rostova, MD (Orthopedics)",
  },
];

export class HealthService {
  getAllArticles(): HealthArticle[] {
    return HEALTH_ARTICLES;
  }

  getArticleBySlug(slug: string): HealthArticle | undefined {
    return HEALTH_ARTICLES.find((a) => a.slug === slug);
  }
}

export const healthService = new HealthService();
