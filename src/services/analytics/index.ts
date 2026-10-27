import { ClinicAnalytics, DepartmentStats, HourlyThroughput } from "@/types";
import { getAuthHeaders } from "@/services/doctors";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BackendDepartmentMetric {
  id: string;
  name: string;
  code?: string | null;
  active_doctors: number;
  total_waiting: number;
  mean_wait_minutes: number;
  p90_wait_minutes: number;
  urgent_cases_count: number;
  current_bottleneck?: string | null;
}

export interface BackendHourlyMetric {
  hour: string;
  arrivals: number;
  completed: number;
}

export interface BackendAdminAnalyticsOverviewResponse {
  total_patients_today: number;
  active_queue_count: number;
  in_consultation_count: number;
  completed_today: number;
  mean_wait_minutes: number;
  p90_wait_minutes: number;
  urgent_delay_rate: number;
  doctor_utilization_rate: number;
  punctuality_rate: number;
  departments: BackendDepartmentMetric[];
  hourly_flow: BackendHourlyMetric[];
}

export interface AdminAnalyticsData {
  analytics: ClinicAnalytics;
  departments: DepartmentStats[];
  hourlyFlow: HourlyThroughput[];
}

export class AnalyticsService {
  async getOverview(): Promise<AdminAnalyticsData> {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}/api/v1/admin/analytics/overview`, {
      method: "GET",
      headers,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || err.message || `Failed to fetch analytics (HTTP ${res.status})`);
    }

    const data: BackendAdminAnalyticsOverviewResponse = await res.json();

    const analytics: ClinicAnalytics = {
      totalPatientsToday: data.total_patients_today,
      activeQueueCount: data.active_queue_count,
      inConsultationCount: data.in_consultation_count,
      completedToday: data.completed_today,
      meanWaitMinutes: data.mean_wait_minutes,
      p90WaitMinutes: data.p90_wait_minutes,
      urgentDelayRate: data.urgent_delay_rate,
      doctorUtilizationRate: data.doctor_utilization_rate,
      punctualityRate: data.punctuality_rate,
    };

    const departments: DepartmentStats[] = (data.departments || []).map((d) => ({
      id: d.id,
      name: d.name,
      activeDoctors: d.active_doctors,
      totalWaiting: d.total_waiting,
      meanWaitMinutes: d.mean_wait_minutes,
      p90WaitMinutes: d.p90_wait_minutes,
      urgentCasesCount: d.urgent_cases_count,
      currentBottleneck: d.current_bottleneck || undefined,
    }));

    const hourlyFlow: HourlyThroughput[] = (data.hourly_flow || []).map((h) => ({
      hour: h.hour,
      arrivals: h.arrivals,
      completed: h.completed,
    }));

    return { analytics, departments, hourlyFlow };
  }
}

export const analyticsService = new AnalyticsService();

