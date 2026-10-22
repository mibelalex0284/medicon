"use client";

import React, { useState, useEffect } from "react";
import { doctorService, DoctorResponse } from "@/services/doctors";
import {
  Stethoscope,
  Search,
  CheckCircle2,
  XCircle,
  Building2,
  Award,
  Star,
  RotateCcw,
  AlertCircle,
  ShieldAlert,
  Users,
  Filter,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function AdminDoctorsPage() {
  const [doctors, setDoctors] = useState<DoctorResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAuthForbidden, setIsAuthForbidden] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  const loadDoctors = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    setIsAuthForbidden(false);

    try {
      const data = await doctorService.listDoctorsAdmin();
      setDoctors(data || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load registered physicians";
      if (msg.includes("403") || msg.includes("Forbidden") || msg.includes("INSUFFICIENT_ROLE_PERMISSIONS")) {
        setIsAuthForbidden(true);
        setErrorMessage("Administrative access restricted. Only authorized system administrators may view physician credentials.");
      } else {
        setErrorMessage(msg);
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadDoctors();
  }, []);

  const filteredDoctors = doctors.filter((doc) => {
    if (statusFilter === "active" && !doc.is_active) return false;
    if (statusFilter === "inactive" && doc.is_active) return false;

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const nameMatch = doc.profile?.full_name?.toLowerCase().includes(q) ?? false;
      const emailMatch = doc.profile?.email?.toLowerCase().includes(q) ?? false;
      const licenseMatch = doc.license_number?.toLowerCase().includes(q) ?? false;
      const deptMatch = doc.department?.name?.toLowerCase().includes(q) ?? false;
      const specMatch = doc.specialties?.some((s) =>
        s.specialty?.name?.toLowerCase().includes(q)
      ) ?? false;

      return nameMatch || emailMatch || licenseMatch || deptMatch || specMatch;
    }

    return true;
  });

  const totalActive = doctors.filter((d) => d.is_active).length;
  const uniqueSpecialties = new Set(
    doctors.flatMap((d) => d.specialties?.map((s) => s.specialty?.name).filter(Boolean))
  ).size;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <span className="text-xs font-semibold text-sky-700 uppercase tracking-wider">
            Clinical Workforce Management
          </span>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 tracking-tight">
            Registered Physicians
          </h1>
          <p className="text-sm text-slate-500">
            Authoritative directory of registered clinical specialists and department affiliations.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={loadDoctors}
            disabled={isLoading}
            className="gap-2 text-xs"
          >
            <RotateCcw size={14} className={isLoading ? "animate-spin" : ""} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Total Registered
              </span>
              <Users size={16} className="text-sky-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {doctors.length}
            </p>
            <span className="text-[11px] text-slate-500 block">
              Across all hospital departments
            </span>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Active Practicing
              </span>
              <CheckCircle2 size={16} className="text-emerald-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {totalActive}
            </p>
            <span className="text-[11px] text-emerald-600 font-medium block">
              Available for outpatient consultations
            </span>
          </CardContent>
        </Card>

        <Card className="border-slate-200 bg-white">
          <CardContent className="p-4 space-y-1">
            <div className="flex items-center justify-between text-slate-500">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Specialties Covered
              </span>
              <Award size={16} className="text-indigo-600" />
            </div>
            <p className="text-3xl font-black text-slate-900 tabular-nums">
              {uniqueSpecialties}
            </p>
            <span className="text-[11px] text-slate-500 block">
              Clinical specialty domains represented
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-slate-200 shadow-2xs">
        <div className="relative flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search by physician name, license, specialty, or email..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sky-500 text-slate-800"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500 font-medium flex items-center gap-1">
            <Filter size={13} />
            Status:
          </span>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "all" | "active" | "inactive")}
            aria-label="Filter physicians by status"
            className="text-xs border border-slate-200 rounded-lg px-2.5 py-1.5 bg-slate-50 text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="all">All Doctors</option>
            <option value="active">Active Only</option>
            <option value="inactive">Inactive Only</option>
          </select>
        </div>
      </div>

      {/* Main Table Content / States */}
      {isLoading ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-sky-50 text-sky-600 animate-spin">
            <Stethoscope size={24} />
          </div>
          <h3 className="text-sm font-bold text-slate-800">
            Loading Physician Directory...
          </h3>
          <p className="text-xs text-slate-500">
            Retrieving authenticated provider records from backend database.
          </p>
        </div>
      ) : isAuthForbidden ? (
        <div className="bg-white rounded-2xl border border-rose-200 p-8 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-rose-50 text-rose-600">
            <ShieldAlert size={26} />
          </div>
          <h3 className="text-base font-bold text-rose-950">
            Administrative Access Required
          </h3>
          <p className="text-xs text-rose-700 max-w-md mx-auto">
            {errorMessage}
          </p>
          <div className="pt-2">
            <Button size="sm" variant="outline" onClick={loadDoctors}>
              Retry with Admin Credentials
            </Button>
          </div>
        </div>
      ) : errorMessage ? (
        <div className="bg-white rounded-2xl border border-amber-200 p-8 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-amber-50 text-amber-600">
            <AlertCircle size={24} />
          </div>
          <h3 className="text-base font-bold text-amber-950">
            Failed to Load Directory
          </h3>
          <p className="text-xs text-amber-800 max-w-md mx-auto">
            {errorMessage}
          </p>
          <div className="pt-2">
            <Button size="sm" variant="outline" onClick={loadDoctors}>
              Try Again
            </Button>
          </div>
        </div>
      ) : filteredDoctors.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-12 text-center space-y-3">
          <div className="inline-flex p-3 rounded-full bg-slate-100 text-slate-400">
            <Stethoscope size={26} />
          </div>
          <h3 className="text-base font-bold text-slate-800">
            No Physicians Found
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery
              ? `No registered physicians match "${searchQuery}". Try adjusting your search query or filters.`
              : "No doctor records currently exist in the database."}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider font-semibold">
                <tr>
                  <th className="px-5 py-3.5">Doctor & Profile</th>
                  <th className="px-4 py-3.5">Specialties</th>
                  <th className="px-4 py-3.5">Department & Facility</th>
                  <th className="px-4 py-3.5">Experience & Rating</th>
                  <th className="px-4 py-3.5">Consultation & Lang</th>
                  <th className="px-4 py-3.5 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDoctors.map((doc) => {
                  const initials = (doc.profile?.full_name || "Doctor")
                    .replace("Dr. ", "")
                    .split(" ")
                    .map((n) => n[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase();

                  const primarySpec = doc.specialties?.find((s) => s.is_primary)?.specialty?.name;
                  const secondarySpecs = doc.specialties
                    ?.filter((s) => !s.is_primary)
                    ?.map((s) => s.specialty?.name)
                    .filter(Boolean);

                  return (
                    <tr key={doc.id} className="hover:bg-slate-50/80 transition-colors">
                      {/* Name & Profile */}
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="h-10 w-10 rounded-xl bg-sky-100 text-sky-800 font-bold flex items-center justify-center shrink-0 border border-sky-200">
                            {initials}
                          </div>
                          <div className="space-y-0.5">
                            <span className="font-bold text-slate-900 block text-sm">
                              {doc.profile?.full_name || "Unknown Doctor"}
                            </span>
                            <span className="text-[11px] text-slate-500 block">
                              {doc.profile?.email || "No email on record"}
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono block">
                              License: {doc.license_number}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Specialties */}
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          {primarySpec ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200">
                              <Award size={11} />
                              {primarySpec} (Primary)
                            </span>
                          ) : (
                            <span className="text-slate-400 italic text-[11px]">
                              General Practice
                            </span>
                          )}

                          {secondarySpecs && secondarySpecs.length > 0 && (
                            <div className="flex flex-wrap gap-1 pt-0.5">
                              {secondarySpecs.map((spec, i) => (
                                <span
                                  key={i}
                                  className="text-[10px] font-medium bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded"
                                >
                                  {spec}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Department & Hospital */}
                      <td className="px-4 py-4">
                        <div className="space-y-0.5">
                          <span className="font-medium text-slate-800 block">
                            {doc.department?.name || "Outpatient Department"}
                          </span>
                          <span className="text-[11px] text-slate-500 flex items-center gap-1">
                            <Building2 size={12} className="text-slate-400" />
                            {doc.hospital?.name || "Metro Central Hospital"}
                          </span>
                        </div>
                      </td>

                      {/* Experience & Rating */}
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          <span className="font-medium text-slate-800 block">
                            {doc.years_of_experience} Years Exp.
                          </span>
                          <div className="flex items-center gap-1 text-[11px] text-slate-600">
                            <Star size={12} className="text-amber-500 fill-amber-500" />
                            <span className="font-semibold">
                              {doc.average_rating > 0 ? doc.average_rating.toFixed(1) : "—"}
                            </span>
                            {doc.rating_count > 0 && (
                              <span className="text-slate-400">({doc.rating_count})</span>
                            )}
                          </div>
                        </div>
                      </td>

                      {/* Consultation Mode & Languages */}
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          <span className="inline-block text-[11px] font-medium text-slate-700 capitalize bg-slate-100 px-2 py-0.5 rounded">
                            {doc.consultation_mode.replace("_", " ")}
                          </span>
                          <span className="text-[10px] text-slate-400 uppercase tracking-wide block">
                            Lang: {doc.languages || "EN"}
                          </span>
                        </div>
                      </td>

                      {/* Active Status */}
                      <td className="px-4 py-4 text-right">
                        {doc.is_active ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
                            <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                            Inactive
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
