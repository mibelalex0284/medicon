"use client";

import React, { useState } from "react";
import { healthService } from "@/services/health";
import { HealthArticle } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  BookOpen,
  ExternalLink,
  ShieldCheck,
  Calendar,
  UserCheck,
  Search,
  HelpCircle,
} from "lucide-react";

export default function PatientHealthPage() {
  const articles = healthService.getAllArticles();
  const [selectedArticle, setSelectedArticle] = useState<HealthArticle | null>(
    articles[0]
  );
  const [searchQuery, setSearchQuery] = useState("");

  const filtered = articles.filter(
    (a) =>
      a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      {/* Education Header */}
      <div>
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-teal-100 text-teal-800 text-xs font-semibold mb-2">
          <BookOpen size={14} />
          Grounded Clinical Education
        </div>
        <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
          Evidence-Based Health Guides
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          Peer-reviewed medical guidance, accredited clinical citations, and
          actionable recovery protocols.
        </p>
      </div>

      {/* Critical Medical Disclaimer */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 text-xs text-slate-600 space-y-1 shadow-2xs">
        <span className="font-bold text-slate-800 flex items-center gap-1.5">
          <ShieldCheck size={15} className="text-teal-600" />
          Clinical Education Notice (Not a Diagnosis)
        </span>
        <p className="leading-relaxed">
          The educational materials provided here are grounded in published clinical guidelines.
          They are intended for patient understanding and self-care navigation, not as an individual
          medical diagnosis. Always consult your attending physician for personalized medical advice.
        </p>
      </div>

      {/* Article List and Detailed View */}
      <div className="space-y-4">
        {filtered.map((article) => {
          const isExpanded = selectedArticle?.id === article.id;
          return (
            <Card
              key={article.id}
              className={`border transition-all overflow-hidden ${
                isExpanded
                  ? "border-teal-500 shadow-sm ring-1 ring-teal-200 bg-white"
                  : "border-slate-200 hover:border-slate-300 bg-white"
              }`}
            >
              <CardContent className="p-5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-teal-700 bg-teal-50 px-2 py-0.5 rounded border border-teal-200">
                      {article.category}
                    </span>
                    <h2
                      onClick={() => setSelectedArticle(article)}
                      className="text-base md:text-lg font-bold text-slate-900 cursor-pointer hover:text-teal-700 transition-colors pt-1"
                    >
                      {article.title}
                    </h2>
                  </div>
                </div>

                <p className="text-xs md:text-sm text-slate-600 leading-relaxed">
                  {article.summary}
                </p>

                {/* Grounded Content When Selected */}
                {isExpanded && (
                  <div className="pt-3 border-t border-slate-100 space-y-4 animate-in fade-in">
                    <div className="space-y-2.5">
                      <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                        Clinical Insights & Best Practices:
                      </h3>
                      {article.content.map((point, idx) => (
                        <div
                          key={idx}
                          className="flex items-start gap-2.5 text-xs text-slate-700 leading-relaxed"
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-teal-600 mt-1.5 shrink-0" />
                          <span>{point}</span>
                        </div>
                      ))}
                    </div>

                    {/* Verifiable Source & Citation Block */}
                    <div className="p-3.5 bg-slate-50 rounded-xl border border-slate-200 space-y-2 text-xs">
                      <div className="flex flex-wrap items-center justify-between gap-2 text-slate-500">
                        <span className="font-semibold text-slate-700 flex items-center gap-1">
                          Source: {article.sourceName}
                        </span>
                        <span className="flex items-center gap-1 font-mono text-[11px]">
                          <Calendar size={12} />
                          {article.freshnessDate}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-600 font-serif italic border-l-2 border-slate-300 pl-2">
                        Citation: &ldquo;{article.citation}&rdquo;
                      </p>
                      <div className="pt-1 flex items-center justify-between text-[11px]">
                        <span className="text-teal-700 font-medium flex items-center gap-1">
                          <UserCheck size={12} />
                          Reviewed by {article.reviewedBy}
                        </span>
                        <a
                          href={article.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-teal-700 hover:underline inline-flex items-center gap-1 font-medium"
                        >
                          Publisher Guidelines
                          <ExternalLink size={12} />
                        </a>
                      </div>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
