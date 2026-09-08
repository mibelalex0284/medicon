import React from "react";
import { Badge } from "@/components/ui/badge";
import { AppointmentStatus, QueueStatus, TriageUrgency } from "@/types";

export function QueueStatusBadge({ status }: { status: QueueStatus }) {
  const configs: Record<
    QueueStatus,
    { label: string; variant: "default" | "warning" | "success" | "secondary" | "danger" }
  > = {
    waiting: { label: "Waiting in Queue", variant: "default" },
    called: { label: "Called — Enter Room", variant: "warning" },
    in_consultation: { label: "In Consultation", variant: "success" },
    completed: { label: "Completed", variant: "secondary" },
    no_show: { label: "No Show", variant: "danger" },
  };

  const config = configs[status] || { label: status, variant: "secondary" };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

export const StatusBadge = QueueStatusBadge;


export function AppointmentStatusBadge({ status }: { status: AppointmentStatus }) {
  const configs: Record<
    AppointmentStatus,
    { label: string; variant: "default" | "warning" | "success" | "secondary" | "danger" }
  > = {
    scheduled: { label: "Scheduled", variant: "default" },
    checked_in: { label: "Checked In", variant: "warning" },
    in_consultation: { label: "In Progress", variant: "success" },
    completed: { label: "Completed", variant: "secondary" },
    cancelled: { label: "Cancelled", variant: "danger" },
    no_show: { label: "No Show", variant: "danger" },
  };

  const config = configs[status] || { label: status, variant: "secondary" };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

export function TriageUrgencyBadge({ urgency }: { urgency: TriageUrgency }) {
  const configs: Record<
    TriageUrgency,
    { label: string; variant: "emergency" | "urgent" | "routine" | "secondary" }
  > = {
    emergency: { label: "Emergency Red Flag", variant: "emergency" },
    urgent: { label: "Urgent Care Needed", variant: "urgent" },
    routine: { label: "Routine Outpatient", variant: "routine" },
    self_care: { label: "Self-Care Guidance", variant: "secondary" },
  };

  const config = configs[urgency] || { label: urgency, variant: "secondary" };
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
