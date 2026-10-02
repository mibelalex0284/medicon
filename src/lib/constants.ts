/**
 * Centralized emergency contact configuration for CareRoute-X.
 * Configured for India (Unified National Emergency Helpline 112 & Ambulance 108/102).
 */
export const EMERGENCY_CONTACT = {
  primaryNumber: "112",
  ambulanceNumber: "108",
  displayLabel: "Call Emergency Services (112)",
  hotlineText: "112 / 108 (Ambulance)",
  guidanceText: "Proceed immediately to the nearest Emergency Department or dial 112 / 108.",
} as const;
