import React from "react";
import { Clock, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface WaitEstimateProps {
  min?: number;
  max?: number;
  estimate?: { min: number; max: number };
  positionAhead?: number;
  compact?: boolean;
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
  showExplanation?: boolean;
  className?: string;
}

export function WaitEstimate({
  min,
  max,
  estimate,
  positionAhead,
  compact = false,
  size = "md",
  showIcon = true,
  showExplanation = false,
  className,
}: WaitEstimateProps) {
  const actualMin = estimate ? estimate.min : min ?? 0;
  const actualMax = estimate ? estimate.max : max ?? 0;

  // Ensure range format: never collapse into a deceptive single exact integer
  const formattedRange = actualMin === actualMax ? `~${actualMin} min` : `${actualMin}–${actualMax} min`;

  const sizeStyles = {
    sm: "text-xs font-medium px-2 py-0.5",
    md: "text-sm font-semibold px-2.5 py-1",
    lg: "text-lg font-bold px-3 py-1.5",
  };

  const iconSizes = {
    sm: 12,
    md: 14,
    lg: 18,
  };

  return (
    <div className={cn("inline-flex flex-col gap-0.5", className)}>
      <div
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md bg-slate-100/90 text-slate-800 border border-slate-200/80 select-none",
          sizeStyles[size]
        )}
        title="Predictive range accounting for clinical consultation variability"
      >
        {showIcon && (
          <Clock
            size={iconSizes[size]}
            className="text-slate-500 shrink-0 stroke-[2.2]"
          />
        )}
        <span className="tabular-nums tracking-tight font-medium text-slate-700">
          Est.
        </span>
        <span className="tabular-nums text-slate-900 font-semibold">
          {formattedRange}
        </span>
      </div>
      {showExplanation && (
        <span className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
          <HelpCircle size={10} className="text-slate-400" />
          Range updates dynamically with patient consults
        </span>
      )}
    </div>
  );
}
