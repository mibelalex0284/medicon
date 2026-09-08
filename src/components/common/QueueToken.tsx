import React from "react";
import { cn } from "@/lib/utils";
import { QueueStatus } from "@/types";

interface QueueTokenProps {
  token: string;
  status?: QueueStatus;
  size?: "sm" | "md" | "lg" | "hero";
  className?: string;
}

export function QueueToken({
  token,
  status = "waiting",
  size = "md",
  className,
}: QueueTokenProps) {
  const sizeStyles = {
    sm: "text-xs px-2 py-0.5 font-bold tracking-wider rounded",
    md: "text-base px-3 py-1 font-bold tracking-widest rounded-md",
    lg: "text-xl px-4 py-2 font-black tracking-widest rounded-lg",
    hero: "text-4xl md:text-5xl px-6 py-3 font-black tracking-widest rounded-xl shadow-xs",
  };

  const statusStyles: Record<QueueStatus, string> = {
    waiting: "bg-sky-50 text-sky-900 border border-sky-300",
    called: "bg-amber-50 text-amber-900 border-2 border-amber-500 animate-pulse",
    in_consultation: "bg-emerald-50 text-emerald-900 border border-emerald-400",
    completed: "bg-slate-100 text-slate-500 border border-slate-200",
    no_show: "bg-rose-50 text-rose-700 border border-rose-200 opacity-60",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center justify-center font-mono select-all uppercase",
        statusStyles[status],
        sizeStyles[size],
        className
      )}
      aria-label={`Queue Token ${token}`}
    >
      {token}
    </div>
  );
}
