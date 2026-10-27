"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Mic,
  MicOff,
  ArrowRight,
  HelpCircle,
  Clock,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export default function FindCarePage() {
  const router = useRouter();
  const [concern, setConcern] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [quickPrompts] = useState([
    "Persistent dry cough for several days",
    "Dull ache in lower back after lifting",
    "Headache and light sensitivity for 2 days",
    "Digestive discomfort after meals",
  ]);

  const toggleVoice = () => {
    if (isListening) {
      setIsListening(false);
    } else {
      setIsListening(true);
      // Simulated speech-to-text progression
      setTimeout(() => {
        setConcern("I have had a worsening dry cough and slight chest tightness for 4 days.");
        setIsListening(false);
      }, 1500);
    }
  };

  const handleContinue = (e: React.FormEvent) => {
    e.preventDefault();
    if (!concern.trim()) return;

    // Pass concern to triage session via query or sessionStorage
    if (typeof window !== "undefined") {
      sessionStorage.setItem("careroute_patient_concern", concern.trim());
    }
    router.push(`/patient/triage?concern=${encodeURIComponent(concern.trim())}`);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Top indicator */}
      <div className="flex items-center gap-2 text-xs font-semibold text-sky-700 tracking-wider uppercase">
        <Sparkles size={14} />
        Step 1 of 3: Care Direction
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          What brings you in today?
        </h1>
        <p className="text-sm text-slate-600 leading-relaxed">
          Describe your symptoms, how long you’ve felt unwell, or what you need
          help with. We will guide you through a clinical intake before matching
          you with a physician.
        </p>
      </div>

      {/* Primary Input Container */}
      <form onSubmit={handleContinue} className="space-y-4">
        <div className="relative rounded-2xl border-2 border-slate-200 bg-white p-4 focus-within:border-sky-500 focus-within:ring-2 focus-within:ring-sky-100 transition-all shadow-xs">
          <textarea
            rows={4}
            value={concern}
            onChange={(e) => setConcern(e.target.value)}
            placeholder="e.g., I've had a persistent dry cough and throat irritation for 4 days, especially at night..."
            className="w-full resize-none border-none bg-transparent text-base text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-0 leading-relaxed"
            autoFocus
          />

          <div className="flex items-center justify-between pt-3 border-t border-slate-100 mt-2">
            <button
              type="button"
              onClick={toggleVoice}
              className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                isListening
                  ? "bg-rose-100 text-rose-800 animate-pulse border border-rose-300"
                  : "bg-slate-100 hover:bg-slate-200 text-slate-700"
              }`}
            >
              {isListening ? (
                <>
                  <MicOff size={15} />
                  Listening... Speak clearly
                </>
              ) : (
                <>
                  <Mic size={15} />
                  Voice Input (Optional)
                </>
              )}
            </button>

            <span className="text-[11px] text-slate-400 font-mono">
              {concern.length} chars
            </span>
          </div>
        </div>

        {/* Quick Common Concerns Suggestions */}
        <div className="space-y-2 pt-1">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
            Common examples to start with:
          </span>
          <div className="flex flex-wrap gap-2">
            {quickPrompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => setConcern(prompt)}
                className="text-xs bg-slate-100 hover:bg-sky-50 hover:text-sky-800 text-slate-700 px-3 py-1.5 rounded-lg border border-slate-200/80 transition-colors text-left"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>

        {/* Continue CTA */}
        <div className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck size={16} className="text-emerald-600 shrink-0" />
            <span>Strict clinical privacy · Reviewed by medical team</span>
          </div>

          <Button
            type="submit"
            size="lg"
            disabled={!concern.trim()}
            className="w-full sm:w-auto font-semibold gap-2 shadow-sm"
          >
            Continue to Guided Triage
            <ArrowRight size={16} />
          </Button>
        </div>
      </form>

      {/* Safety Notice */}
      <div className="rounded-xl bg-slate-100/70 p-3.5 border border-slate-200/80 flex items-start gap-3 text-xs text-slate-600">
        <HelpCircle size={16} className="text-slate-400 shrink-0 mt-0.5" />
        <p>
          MediLink is designed for outpatient clinic navigation. If you are
          experiencing sudden crushing chest pain, paralysis, or severe respiratory distress,
          please proceed directly to an emergency department or call emergency services.
        </p>
      </div>
    </div>
  );
}
