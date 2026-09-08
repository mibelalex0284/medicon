import { ClinicAnalytics, DepartmentStats } from "@/types";

export const CLINIC_DEPARTMENTS: DepartmentStats[] = [
  {
    id: "dep_adult_opd",
    name: "Adult Outpatient & Internal Med",
    activeDoctors: 4,
    totalWaiting: 14,
    meanWaitMinutes: 24,
    p90WaitMinutes: 42,
    urgentCasesCount: 2,
    currentBottleneck: "Room 204 high complexity intake",
  },
  {
    id: "dep_cardio",
    name: "Cardiovascular Pavilion",
    activeDoctors: 3,
    totalWaiting: 9,
    meanWaitMinutes: 32,
    p90WaitMinutes: 55,
    urgentCasesCount: 3,
    currentBottleneck: "ECG diagnostic room throughput",
  },
  {
    id: "dep_ortho",
    name: "Musculoskeletal & Orthopedics",
    activeDoctors: 2,
    totalWaiting: 6,
    meanWaitMinutes: 18,
    p90WaitMinutes: 30,
    urgentCasesCount: 0,
  },
  {
    id: "dep_peds",
    name: "Pediatrics & Adolescent Care",
    activeDoctors: 3,
    totalWaiting: 8,
    meanWaitMinutes: 15,
    p90WaitMinutes: 28,
    urgentCasesCount: 1,
  },
];

export class AnalyticsService {
  getClinicAnalytics(): ClinicAnalytics {
    return {
      totalPatientsToday: 68,
      activeQueueCount: 37,
      inConsultationCount: 12,
      completedToday: 19,
      meanWaitMinutes: 22,
      p90WaitMinutes: 38,
      urgentDelayRate: 3.8, // 3.8%
      doctorUtilizationRate: 88.5, // 88.5%
      punctualityRate: 91.2, // 91.2%
    };
  }

  getDepartmentStats(): DepartmentStats[] {
    return CLINIC_DEPARTMENTS;
  }

  runSimulation(scenario: {
    doctorCapacityChange: number; // e.g. -2, 0, +2
    consultationDurationAvg: number; // e.g. 15
    appointmentVolumeMultiplier: number; // e.g. 1.2
  }): {
    projectedMeanWait: number;
    projectedP90Wait: number;
    projectedUtilization: number;
    projectedUrgentDelay: number;
    riskAssessment: "low" | "moderate" | "critical";
  } {
    // Isolated queue simulation model
    const baseWait = 22;
    const baseP90 = 38;

    const capacityFactor = 1 - scenario.doctorCapacityChange * 0.12;
    const durationFactor = scenario.consultationDurationAvg / 15;
    const volumeFactor = scenario.appointmentVolumeMultiplier;

    const projectedMean = Math.round(baseWait * capacityFactor * durationFactor * volumeFactor);
    const projectedP90 = Math.round(baseP90 * capacityFactor * durationFactor * volumeFactor);
    const projectedUtilization = Math.min(
      99,
      Math.round(88 * durationFactor * (volumeFactor / Math.max(0.5, 1 + scenario.doctorCapacityChange * 0.1)))
    );
    const projectedUrgentDelay = +(
      3.8 *
      Math.max(0.6, volumeFactor * (durationFactor > 1.1 ? 1.4 : 1))
    ).toFixed(1);

    let risk: "low" | "moderate" | "critical" = "low";
    if (projectedMean > 35 || projectedUtilization > 92) risk = "moderate";
    if (projectedMean > 50 || projectedUtilization > 95 || projectedUrgentDelay > 8)
      risk = "critical";

    return {
      projectedMeanWait: Math.max(8, projectedMean),
      projectedP90Wait: Math.max(15, projectedP90),
      projectedUtilization,
      projectedUrgentDelay,
      riskAssessment: risk,
    };
  }
}

export const analyticsService = new AnalyticsService();
