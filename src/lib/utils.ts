import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatWaitRange(minMinutes: number, maxMinutes: number): string {
  if (minMinutes === maxMinutes) {
    return `~${minMinutes} min`;
  }
  return `${minMinutes}–${maxMinutes} min`;
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(amount);
}
