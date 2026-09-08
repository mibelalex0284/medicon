import React from "react";
import { AlertOctagon, PhoneCall, ShieldAlert } from "lucide-react";
import { RedFlagAlert } from "@/types";

interface EmergencyBannerProps {
  alert: RedFlagAlert;
  onDismiss?: () => void;
}

export function EmergencyBanner({ alert, onDismiss }: EmergencyBannerProps) {
  if (!alert.isTriggered) return null;

  return (
    <div
      role="alert"
      className="w-full rounded-xl border-2 border-red-600 bg-red-50 p-4 md:p-5 text-red-950 shadow-md emergency-pulse mb-6"
    >
      <div className="flex items-start gap-3.5">
        <div className="p-2 bg-red-600 text-white rounded-lg shrink-0 mt-0.5">
          <AlertOctagon size={24} className="stroke-[2.5]" />
        </div>
        <div className="space-y-1.5 flex-1">
          <div className="flex items-center justify-between">
            <h4 className="font-bold text-base md:text-lg text-red-900 tracking-tight flex items-center gap-2">
              <ShieldAlert size={18} className="text-red-700" />
              {alert.title}
            </h4>
            <span className="text-[11px] font-bold uppercase tracking-wider bg-red-200/80 text-red-900 px-2 py-0.5 rounded border border-red-300">
              Immediate Attention
            </span>
          </div>

          <p className="text-sm text-red-900 leading-relaxed font-medium">
            {alert.message}
          </p>

          <div className="mt-3 p-3 bg-white/90 border border-red-300 rounded-lg text-xs md:text-sm text-red-950 font-semibold space-y-1">
            <p className="text-slate-700 font-normal">Recommended action:</p>
            <p className="text-red-900 font-bold">{alert.actionRecommendation}</p>
          </div>

          <div className="pt-2 flex flex-wrap items-center gap-3">
            <a
              href="tel:911"
              className="inline-flex items-center gap-2 px-4 py-2 bg-red-700 hover:bg-red-800 text-white text-sm font-bold rounded-lg shadow-sm transition-colors"
            >
              <PhoneCall size={16} />
              Call Emergency Services (911)
            </a>
            {alert.hotline && (
              <a
                href={`tel:${alert.hotline}`}
                className="inline-flex items-center gap-2 px-3 py-2 bg-white text-red-800 border border-red-400 text-xs md:text-sm font-semibold rounded-lg hover:bg-red-100 transition-colors"
              >
                Direct Triage Hotline: {alert.hotline}
              </a>
            )}
          </div>

          <p className="text-[11px] text-red-700/90 pt-1">
            CareRoute-X provides clinical guidance and triage navigation. This is not a final medical diagnosis.
          </p>
        </div>
      </div>
    </div>
  );
}
