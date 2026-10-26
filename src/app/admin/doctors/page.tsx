"use client";

import React, { useState, useEffect, useMemo } from "react";
import {
  doctorService,
  DoctorResponse,
  HospitalResponse,
  DepartmentResponse,
  SpecialtyResponse,
  DoctorScheduleItem,
} from "@/services/doctors";
import { authService } from "@/services/auth";
import { useAuth } from "@/context/AuthContext";
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
  UserPlus,
  Calendar,
  X,
  Phone,
  Layers,
  Lock,
  Loader2,
  Check,
  UserX,
  UserCheck,
  Trash2,
  KeyRound,
  Copy,
  AlertTriangle,
  ShieldCheck,
  Clock,
  Eye,
  EyeOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export default function AdminDoctorsPage() {
  const { user } = useAuth();

  const [doctors, setDoctors] = useState<DoctorResponse[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isAuthForbidden, setIsAuthForbidden] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"all" | "active" | "inactive">("all");

  // Metadata Lookups (Hospitals, Departments, Specialties)
  const [hospitals, setHospitals] = useState<HospitalResponse[]>([]);
  const [departments, setDepartments] = useState<DepartmentResponse[]>([]);
  const [specialties, setSpecialties] = useState<SpecialtyResponse[]>([]);
  const [isLoadingLookups, setIsLoadingLookups] = useState<boolean>(false);
  const [isLoadingDepartments, setIsLoadingDepartments] = useState<boolean>(false);
  const [specialtySearch, setSpecialtySearch] = useState<string>("");

  // Onboarding Modal Form State
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [onboardFullName, setOnboardFullName] = useState("");
  const [onboardEmail, setOnboardEmail] = useState("");
  const [onboardPassword, setOnboardPassword] = useState("");
  const [onboardConfirmPassword, setOnboardConfirmPassword] = useState("");
  const [showOnboardPassword, setShowOnboardPassword] = useState(false);
  const [showOnboardConfirmPassword, setShowOnboardConfirmPassword] = useState(false);
  const [onboardLicense, setOnboardLicense] = useState("");
  const [onboardPhone, setOnboardPhone] = useState("");
  const [onboardHospitalId, setOnboardHospitalId] = useState("");
  const [onboardDepartmentId, setOnboardDepartmentId] = useState("");
  const [onboardSpecialtyIds, setOnboardSpecialtyIds] = useState<string[]>([]);
  const [onboardPrimarySpecialtyId, setOnboardPrimarySpecialtyId] = useState<string>("");
  const [onboardExperience, setOnboardExperience] = useState(5);
  const [onboardMode, setOnboardMode] = useState("both");
  const [onboardLanguages, setOnboardLanguages] = useState("en");

  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [isOnboardSubmitting, setIsOnboardSubmitting] = useState(false);
  const [onboardError, setOnboardError] = useState<string | null>(null);
  const [onboardSuccess, setOnboardSuccess] = useState<string | null>(null);
  const [onboardActionLink, setOnboardActionLink] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);

  // Status Modal State (Deactivate / Reactivate)
  const [statusModalOpen, setStatusModalOpen] = useState(false);
  const [selectedDoctorForStatus, setSelectedDoctorForStatus] = useState<DoctorResponse | null>(null);
  const [statusModalReason, setStatusModalReason] = useState("");
  const [isStatusSubmitting, setIsStatusSubmitting] = useState(false);
  const [statusModalError, setStatusModalError] = useState<string | null>(null);

  // Delete Modal State
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [selectedDoctorForDelete, setSelectedDoctorForDelete] = useState<DoctorResponse | null>(null);
  const [isDeleteSubmitting, setIsDeleteSubmitting] = useState(false);
  const [deleteModalError, setDeleteModalError] = useState<string | null>(null);
  const [deleteHasClinicalHistory, setDeleteHasClinicalHistory] = useState(false);

  // Resend Invite Modal State
  const [resendModalOpen, setResendModalOpen] = useState(false);
  const [selectedDoctorForResend, setSelectedDoctorForResend] = useState<DoctorResponse | null>(null);
  const [resendActionLink, setResendActionLink] = useState<string | null>(null);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendError, setResendError] = useState<string | null>(null);
  const [copiedResendLink, setCopiedResendLink] = useState(false);

  // Global notification banner for actions
  const [actionNotice, setActionNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);

  // Schedule Management Modal State
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [selectedDoctorForSchedule, setSelectedDoctorForSchedule] = useState<DoctorResponse | null>(null);
  const [doctorSchedules, setDoctorSchedules] = useState<DoctorScheduleItem[]>([]);
  const [isLoadingSchedules, setIsLoadingSchedules] = useState(false);
  const [isSavingSchedules, setIsSavingSchedules] = useState(false);
  const [scheduleModalError, setScheduleModalError] = useState<string | null>(null);
  const [scheduleModalSuccess, setScheduleModalSuccess] = useState<string | null>(null);

  // Repair Modal State
  const [repairModalOpen, setRepairModalOpen] = useState(false);
  const [repairLoading, setRepairLoading] = useState(false);
  const [repairDryRunData, setRepairDryRunData] = useState<{
    dry_run: boolean;
    unscheduled_count: number;
    doctors: Array<{ doctor_id: string; doctor_name: string }>;
  } | null>(null);
  const [repairError, setRepairError] = useState<string | null>(null);
  const [repairSuccess, setRepairSuccess] = useState<string | null>(null);

  // Tenant restriction: hospital administrators are locked to user.hospital_id
  const isTenantRestricted = Boolean(user?.hospital_id);
  const effectiveHospitalId = user?.hospital_id || onboardHospitalId;

  // Selected hospital object for display
  const currentHospital = useMemo(() => {
    return hospitals.find((h) => h.id === effectiveHospitalId);
  }, [hospitals, effectiveHospitalId]);

  const loadDoctors = async (overrideStatus?: "all" | "active" | "inactive") => {
    setIsLoading(true);
    setErrorMessage(null);
    setIsAuthForbidden(false);

    try {
      const activeFilter = overrideStatus ?? statusFilter;
      const data = await doctorService.listDoctorsAdmin(effectiveHospitalId || undefined, activeFilter);
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

  const loadLookups = async () => {
    setIsLoadingLookups(true);
    try {
      const [hList, sList] = await Promise.all([
        doctorService.listHospitals().catch(() => [] as HospitalResponse[]),
        doctorService.listSpecialties().catch(() => [] as SpecialtyResponse[]),
      ]);
      setHospitals(hList || []);
      setSpecialties(sList || []);

      if (!user?.hospital_id && hList && hList.length > 0 && !onboardHospitalId) {
        setOnboardHospitalId(hList[0].id);
      }
    } catch (err) {
      console.error("Failed to load hospitals and specialties:", err);
    } finally {
      setIsLoadingLookups(false);
    }
  };

  useEffect(() => {
    loadDoctors();
    loadLookups();
  }, []);

  // Sync hospital ID if user has tenant assignment
  useEffect(() => {
    if (user?.hospital_id) {
      setOnboardHospitalId(user.hospital_id);
    } else if (hospitals.length > 0 && !onboardHospitalId) {
      setOnboardHospitalId(hospitals[0].id);
    }
  }, [user?.hospital_id, hospitals]);

  // Load departments dynamically whenever effective hospital changes
  useEffect(() => {
    if (!effectiveHospitalId) {
      setDepartments([]);
      setOnboardDepartmentId("");
      return;
    }

    let isSubscribed = true;
    setIsLoadingDepartments(true);

    doctorService
      .listDepartments(effectiveHospitalId)
      .then((data) => {
        if (isSubscribed) {
          setDepartments(data || []);
          setOnboardDepartmentId("");
        }
      })
      .catch((err) => {
        console.error("Failed to load departments:", err);
        if (isSubscribed) {
          setDepartments([]);
          setOnboardDepartmentId("");
        }
      })
      .finally(() => {
        if (isSubscribed) {
          setIsLoadingDepartments(false);
        }
      });

    return () => {
      isSubscribed = false;
    };
  }, [effectiveHospitalId]);

  // Specialty selection and primary designation handlers
  const handleToggleSpecialty = (specId: string) => {
    setOnboardSpecialtyIds((prev) => {
      const exists = prev.includes(specId);
      if (exists) {
        const next = prev.filter((id) => id !== specId);
        if (onboardPrimarySpecialtyId === specId) {
          setOnboardPrimarySpecialtyId(next.length > 0 ? next[0] : "");
        }
        return next;
      } else {
        const next = [...prev, specId];
        if (!onboardPrimarySpecialtyId) {
          setOnboardPrimarySpecialtyId(specId);
        }
        return next;
      }
    });

    if (validationErrors.primarySpecialty) {
      setValidationErrors((prev) => {
        const { primarySpecialty, ...rest } = prev;
        return rest;
      });
    }
  };

  const handleSetPrimarySpecialty = (specId: string) => {
    if (!onboardSpecialtyIds.includes(specId)) {
      setOnboardSpecialtyIds((prev) => [...prev, specId]);
    }
    setOnboardPrimarySpecialtyId(specId);

    if (validationErrors.primarySpecialty) {
      setValidationErrors((prev) => {
        const { primarySpecialty, ...rest } = prev;
        return rest;
      });
    }
  };

  const filteredSpecialties = useMemo(() => {
    if (!specialtySearch.trim()) return specialties;
    const q = specialtySearch.toLowerCase();
    return specialties.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.code.toLowerCase().includes(q) ||
        (s.description && s.description.toLowerCase().includes(q))
    );
  }, [specialties, specialtySearch]);

  const validateOnboardForm = (): boolean => {
    const errors: Record<string, string> = {};

    const trimmedName = onboardFullName.trim();
    if (!trimmedName || trimmedName.length < 2) {
      errors.fullName = "Full physician name is required (at least 2 characters).";
    }

    const trimmedEmail = onboardEmail.trim();
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!trimmedEmail || !emailRegex.test(trimmedEmail)) {
      errors.email = "A valid professional email address is required.";
    }

    if (!onboardPassword) {
      errors.password = "Password is required.";
    } else if (onboardPassword.length < 8) {
      errors.password = "Password must be at least 8 characters long.";
    }

    if (!onboardConfirmPassword) {
      errors.confirmPassword = "Confirm password is required.";
    } else if (onboardPassword !== onboardConfirmPassword) {
      errors.confirmPassword = "Passwords do not match.";
    }

    const trimmedLicense = onboardLicense.trim();
    if (!trimmedLicense || trimmedLicense.length < 2) {
      errors.license = "Medical license number is required (at least 2 characters).";
    }

    if (!effectiveHospitalId) {
      errors.hospital = "Hospital facility assignment is required.";
    }

    if (onboardExperience < 0 || isNaN(onboardExperience)) {
      errors.experience = "Years of experience must be 0 or greater.";
    }

    if (!["both", "in_person", "video"].includes(onboardMode)) {
      errors.mode = "Please select a valid consultation mode.";
    }

    if (!onboardLanguages.trim()) {
      errors.languages = "At least one language must be specified.";
    }

    if (
      onboardSpecialtyIds.length > 0 &&
      (!onboardPrimarySpecialtyId || !onboardSpecialtyIds.includes(onboardPrimarySpecialtyId))
    ) {
      errors.primarySpecialty =
        "Please designate exactly one primary specialty among the selected specialties.";
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleOnboardDoctor = async (e: React.FormEvent) => {
    e.preventDefault();
    setOnboardError(null);
    setOnboardSuccess(null);
    setOnboardActionLink(null);

    if (!validateOnboardForm()) {
      return;
    }

    setIsOnboardSubmitting(true);

    try {
      const payload = {
        full_name: onboardFullName.trim(),
        email: onboardEmail.trim(),
        password: onboardPassword,
        license_number: onboardLicense.trim(),
        hospital_id: effectiveHospitalId,
        department_id: onboardDepartmentId ? onboardDepartmentId : null,
        specialty_ids: onboardSpecialtyIds.length > 0 ? onboardSpecialtyIds : [],
        primary_specialty_id:
          onboardSpecialtyIds.length > 0 && onboardPrimarySpecialtyId
            ? onboardPrimarySpecialtyId
            : null,
        years_of_experience: Number(onboardExperience),
        consultation_mode: onboardMode,
        languages: onboardLanguages.trim() || "en",
        phone: onboardPhone.trim() ? onboardPhone.trim() : null,
      };

      const res = await authService.adminOnboardDoctor(payload);

      // Clear both password fields immediately after successful submission
      setOnboardPassword("");
      setOnboardConfirmPassword("");
      setShowOnboardPassword(false);
      setShowOnboardConfirmPassword(false);

      setOnboardSuccess(`Physician ${onboardFullName.trim()} onboarded successfully!`);
      if (res.action_link) {
        setOnboardActionLink(res.action_link);
      }

      // Reload directory
      await loadDoctors();

      // Reset form values if no action link to copy, or retain link display
      if (!res.action_link) {
        setOnboardFullName("");
        setOnboardEmail("");
        setOnboardLicense("");
        setOnboardPhone("");
        setOnboardDepartmentId("");
        setOnboardSpecialtyIds([]);
        setOnboardPrimarySpecialtyId("");
        setValidationErrors({});
        setTimeout(() => {
          setIsOnboardingOpen(false);
          setOnboardSuccess(null);
        }, 2000);
      }
    } catch (err: any) {
      setOnboardError(
        err.message || "Failed to onboard physician. Please check the details and try again."
      );
    } finally {
      setIsOnboardSubmitting(false);
    }
  };

  const handleCloseModal = () => {
    if (isOnboardSubmitting) return;
    setIsOnboardingOpen(false);
    setOnboardPassword("");
    setOnboardConfirmPassword("");
    setShowOnboardPassword(false);
    setShowOnboardConfirmPassword(false);
    setOnboardError(null);
    setOnboardSuccess(null);
    setOnboardActionLink(null);
    setValidationErrors({});
  };

  // Status Update Handler (Deactivate / Reactivate)
  const handleUpdateDoctorStatus = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDoctorForStatus) return;

    setIsStatusSubmitting(true);
    setStatusModalError(null);

    const targetActiveState = !selectedDoctorForStatus.is_active;

    try {
      const res = await doctorService.updateDoctorStatus(
        selectedDoctorForStatus.id,
        targetActiveState,
        statusModalReason.trim() || undefined
      );

      setStatusModalOpen(false);
      setSelectedDoctorForStatus(null);
      setActionNotice({
        type: "success",
        text: `Physician account ${res.full_name} (${res.email}) has been ${res.status}.`,
      });
      setTimeout(() => setActionNotice(null), 5000);

      await loadDoctors();
    } catch (err: any) {
      setStatusModalError(err.message || "Failed to update physician status");
    } finally {
      setIsStatusSubmitting(false);
    }
  };

  // Resend Doctor Invitation Handler
  const handleOpenResendModal = async (doc: DoctorResponse) => {
    setSelectedDoctorForResend(doc);
    setResendActionLink(null);
    setResendError(null);
    setCopiedResendLink(false);
    setResendModalOpen(true);
    setResendLoading(true);

    try {
      const res = await doctorService.resendDoctorInvitation(doc.id);
      if (res.action_link) {
        setResendActionLink(res.action_link);
      }
      setActionNotice({
        type: "success",
        text: `Invitation link regenerated for ${doc.profile?.full_name || doc.license_number}.`,
      });
      setTimeout(() => setActionNotice(null), 5000);
      await loadDoctors();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to regenerate physician invitation";
      setResendError(msg);
    } finally {
      setResendLoading(false);
    }
  };

  // Delete Handler
  const handleDeleteDoctor = async () => {
    if (!selectedDoctorForDelete) return;

    setIsDeleteSubmitting(true);
    setDeleteModalError(null);
    setDeleteHasClinicalHistory(false);

    try {
      const res = await doctorService.deleteDoctor(selectedDoctorForDelete.id);

      setDeleteModalOpen(false);
      setSelectedDoctorForDelete(null);
      setActionNotice({
        type: "success",
        text: `Physician ${res.full_name} (${res.email}) has been permanently deleted.`,
      });
      setTimeout(() => setActionNotice(null), 5000);

      await loadDoctors();
    } catch (err: any) {
      const msg = err.message || "Failed to delete physician record";
      setDeleteModalError(msg);
      if (
        msg.includes("dependent clinical records exist") ||
        msg.includes("CANNOT_DELETE_DOCTOR_WITH_CLINICAL_HISTORY")
      ) {
        setDeleteHasClinicalHistory(true);
      }
    } finally {
      setIsDeleteSubmitting(false);
    }
  };

  const openScheduleModal = async (doctor: DoctorResponse) => {
    setSelectedDoctorForSchedule(doctor);
    setScheduleModalOpen(true);
    setIsLoadingSchedules(true);
    setScheduleModalError(null);
    setScheduleModalSuccess(null);
    try {
      const data = await doctorService.getDoctorSchedules(doctor.id);
      setDoctorSchedules(data || []);
    } catch (err: unknown) {
      setScheduleModalError(
        err instanceof Error ? err.message : "Failed to load doctor consultation schedules."
      );
      setDoctorSchedules([]);
    } finally {
      setIsLoadingSchedules(false);
    }
  };

  const handleInitializeDefaultSchedule = async () => {
    if (!selectedDoctorForSchedule) return;
    setIsSavingSchedules(true);
    setScheduleModalError(null);
    setScheduleModalSuccess(null);
    try {
      const updated = await doctorService.initializeDefaultSchedule(selectedDoctorForSchedule.id, false);
      setDoctorSchedules(updated);
      setScheduleModalSuccess("Default weekday consultation hours (Mon-Fri 09:00 - 17:00) initialized successfully!");
    } catch (err: unknown) {
      setScheduleModalError(
        err instanceof Error ? err.message : "Failed to initialize default schedule."
      );
    } finally {
      setIsSavingSchedules(false);
    }
  };

  const handleSaveSchedules = async () => {
    if (!selectedDoctorForSchedule) return;
    setIsSavingSchedules(true);
    setScheduleModalError(null);
    setScheduleModalSuccess(null);
    try {
      const updated = await doctorService.updateDoctorSchedules(selectedDoctorForSchedule.id, doctorSchedules);
      setDoctorSchedules(updated);
      setScheduleModalSuccess("Consultation schedules updated successfully!");
    } catch (err: unknown) {
      setScheduleModalError(
        err instanceof Error ? err.message : "Failed to update consultation schedules."
      );
    } finally {
      setIsSavingSchedules(false);
    }
  };

  const handleOpenRepairModal = async () => {
    setRepairModalOpen(true);
    setRepairLoading(true);
    setRepairError(null);
    setRepairSuccess(null);
    try {
      const data = await doctorService.repairSchedules(effectiveHospitalId || undefined, true);
      setRepairDryRunData(data);
    } catch (err: unknown) {
      setRepairError(
        err instanceof Error ? err.message : "Failed to preview unscheduled doctors."
      );
    } finally {
      setRepairLoading(false);
    }
  };

  const handleExecuteRepair = async () => {
    setRepairLoading(true);
    setRepairError(null);
    setRepairSuccess(null);
    try {
      const result = await doctorService.repairSchedules(effectiveHospitalId || undefined, false);
      setRepairSuccess(`Successfully repaired ${result.repaired_count} unscheduled doctor(s)!`);
      loadDoctors();
    } catch (err: unknown) {
      setRepairError(
        err instanceof Error ? err.message : "Failed to repair doctor schedules."
      );
    } finally {
      setRepairLoading(false);
    }
  };

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
            Authoritative directory of registered clinical specialists, affiliations, and lifecycle controls.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            id="repair-schedules-btn"
            data-testid="repair-schedules-btn"
            size="sm"
            variant="outline"
            onClick={handleOpenRepairModal}
            className="gap-2 text-xs border-indigo-200 text-indigo-700 hover:bg-indigo-50 font-semibold"
            title="Inspect and repair unscheduled doctors"
          >
            <Calendar size={14} />
            Repair Schedules
          </Button>

          <Button
            id="onboard-physician-btn"
            data-testid="onboard-physician-btn"
            size="sm"
            onClick={() => {
              setIsOnboardingOpen(true);
              setOnboardError(null);
              setOnboardSuccess(null);
              setOnboardActionLink(null);
            }}
            className="gap-2 text-xs bg-sky-700 hover:bg-sky-800 text-white font-semibold"
          >
            <UserPlus size={14} />
            Onboard Physician
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={() => loadDoctors()}
            disabled={isLoading}
            className="gap-2 text-xs"
          >
            <RotateCcw size={14} className={isLoading ? "animate-spin" : ""} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Action Notification Banner */}
      {actionNotice && (
        <div
          id="action-notice-banner"
          data-testid="action-notice-banner"
          className={cn(
            "p-3 rounded-xl border flex items-center justify-between text-xs animate-in fade-in",
            actionNotice.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800 font-semibold"
              : "bg-rose-50 border-rose-200 text-rose-800"
          )}
        >
          <div className="flex items-center gap-2">
            {actionNotice.type === "success" ? (
              <CheckCircle2 size={16} className="text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle size={16} className="text-rose-600 shrink-0" />
            )}
            <span>{actionNotice.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setActionNotice(null)}
            className="text-slate-400 hover:text-slate-600"
          >
            <X size={14} />
          </button>
        </div>
      )}

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
            id="admin-status-filter"
            data-testid="admin-status-filter"
            value={statusFilter}
            onChange={(e) => {
              const val = e.target.value as "all" | "active" | "inactive";
              setStatusFilter(val);
              loadDoctors(val);
            }}
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
            <Button size="sm" variant="outline" onClick={() => loadDoctors()}>
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
            <Button size="sm" variant="outline" onClick={() => loadDoctors()}>
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
              : "No doctor records currently match the selected filters."}
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
                  <th className="px-4 py-3.5">Status</th>
                  <th className="px-4 py-3.5 text-right">Actions</th>
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
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-slate-400 font-mono block">
                                License: {doc.license_number}
                              </span>
                              {doc.profile?.phone && (
                                <span className="text-[10px] text-slate-400 flex items-center gap-0.5">
                                  <Phone size={10} />
                                  {doc.profile.phone}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Specialties */}
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          {primarySpec ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                              <Star size={11} className="fill-amber-500 text-amber-500" />
                              {primarySpec}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">No primary specialty</span>
                          )}

                          {secondarySpecs && secondarySpecs.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {secondarySpecs.map((spec, i) => (
                                <span
                                  key={i}
                                  className="inline-block px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600 font-medium"
                                >
                                  {spec}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Department & Facility */}
                      <td className="px-4 py-4 text-slate-600">
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 font-medium text-slate-800">
                            <Building2 size={13} className="text-slate-400" />
                            {doc.department?.name || "Unassigned Dept"}
                          </div>
                          <span className="text-[11px] text-slate-400 block">
                            Facility: {doc.hospital_id}
                          </span>
                        </div>
                      </td>

                      {/* Experience & Rating */}
                      <td className="px-4 py-4 text-slate-600">
                        <div className="space-y-0.5">
                          <span className="font-semibold text-slate-800 block">
                            {doc.years_of_experience} yrs experience
                          </span>
                          <div className="flex items-center gap-1 text-[11px] text-amber-600 font-bold">
                            <Star size={12} className="fill-amber-400 text-amber-400" />
                            {(doc.average_rating ?? 5.0).toFixed(1)}
                            <span className="text-slate-400 font-normal">
                              ({doc.rating_count ?? 0} reviews)
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Status & Invitation Badge */}
                      <td className="px-4 py-4">
                        <div className="space-y-1">
                          {doc.is_active ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                              Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
                              <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                              Inactive
                            </span>
                          )}

                          {doc.invitation_status === "pending" ? (
                            <span
                              id={`invite-badge-${doc.id}`}
                              data-testid={`invite-badge-${doc.id}`}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 block w-fit"
                              title="Physician invitation sent, pending initial password setup"
                            >
                              <Clock size={10} className="text-amber-600 shrink-0" />
                              Invite Pending
                            </span>
                          ) : (
                            <span
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-sky-50 text-sky-700 border border-sky-200 block w-fit"
                              title="Account credentials provisioned and active"
                            >
                              <CheckCircle2 size={10} className="text-sky-600 shrink-0" />
                              Active
                            </span>
                          )}
                        </div>
                      </td>

                      {/* Actions */}
                      <td className="px-4 py-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <Button
                            id={`resend-invite-doc-${doc.id}`}
                            data-testid={`resend-invite-doc-${doc.id}`}
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenResendModal(doc)}
                            className="text-[11px] h-7 px-2 border-indigo-300 text-indigo-800 hover:bg-indigo-50 gap-1 font-semibold"
                            title="Regenerate secure invitation link"
                          >
                            <KeyRound size={12} />
                            Resend Invite
                          </Button>

                          <Button
                            id={`schedule-doc-${doc.id}`}
                            data-testid={`schedule-doc-${doc.id}`}
                            variant="outline"
                            size="sm"
                            onClick={() => openScheduleModal(doc)}
                            className="text-[11px] h-7 px-2 border-sky-300 text-sky-800 hover:bg-sky-50 gap-1 font-semibold"
                            title="Manage consultation hours & weekly schedules"
                          >
                            <Calendar size={12} />
                            Schedule
                          </Button>

                          {doc.is_active ? (
                            <Button
                              id={`deactivate-doc-${doc.id}`}
                              data-testid={`deactivate-doc-${doc.id}`}
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedDoctorForStatus(doc);
                                setStatusModalReason("");
                                setStatusModalError(null);
                                setStatusModalOpen(true);
                              }}
                              className="text-[11px] h-7 px-2 border-amber-300 text-amber-800 hover:bg-amber-50 gap-1 font-semibold"
                              title="Deactivate physician account"
                            >
                              <UserX size={12} />
                              Deactivate
                            </Button>
                          ) : (
                            <Button
                              id={`reactivate-doc-${doc.id}`}
                              data-testid={`reactivate-doc-${doc.id}`}
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setSelectedDoctorForStatus(doc);
                                setStatusModalReason("");
                                setStatusModalError(null);
                                setStatusModalOpen(true);
                              }}
                              className="text-[11px] h-7 px-2 border-emerald-300 text-emerald-800 hover:bg-emerald-50 gap-1 font-semibold"
                              title="Reactivate physician account"
                            >
                              <UserCheck size={12} />
                              Reactivate
                            </Button>
                          )}

                          <Button
                            id={`delete-doc-${doc.id}`}
                            data-testid={`delete-doc-${doc.id}`}
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setSelectedDoctorForDelete(doc);
                              setDeleteModalError(null);
                              setDeleteHasClinicalHistory(false);
                              setDeleteModalOpen(true);
                            }}
                            className="text-[11px] h-7 px-2 text-rose-600 hover:bg-rose-50 hover:text-rose-700 gap-1 font-semibold"
                            title="Delete physician record"
                          >
                            <Trash2 size={12} />
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Onboard Physician Modal Dialog */}
      {isOnboardingOpen && (
        <div
          id="onboard-physician-modal"
          data-testid="onboard-physician-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-2xl max-h-[92vh] flex flex-col overflow-hidden animate-in zoom-in-95">
            {/* Modal Header */}
            <div className="bg-slate-900 px-6 py-4 text-white flex items-center justify-between border-b border-slate-800 shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-sky-600 text-white shadow-xs">
                  <UserPlus size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-white">Onboard New Physician</h3>
                  <p className="text-[11px] text-slate-400">
                    Administrator-provisioned clinical specialist record and facility affiliation
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={handleCloseModal}
                disabled={isOnboardSubmitting}
                className="text-slate-400 hover:text-white p-1 rounded-lg transition-colors"
                aria-label="Close modal"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <form onSubmit={handleOnboardDoctor} className="p-6 space-y-5 text-xs overflow-y-auto flex-1">
              {/* API Error Alert */}
              {onboardError && (
                <div
                  id="onboard-api-error"
                  data-testid="onboard-api-error"
                  className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-700 flex items-start gap-2.5 shadow-2xs"
                >
                  <AlertCircle size={16} className="text-rose-500 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Onboarding Failed</span>
                    <span className="text-[11px] leading-relaxed">{onboardError}</span>
                  </div>
                </div>
              )}

              {/* Success Alert */}
              {onboardSuccess && (
                <div
                  id="onboard-api-success"
                  data-testid="onboard-api-success"
                  className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 font-semibold flex items-center gap-2.5 shadow-2xs"
                >
                  <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
                  <span>{onboardSuccess}</span>
                </div>
              )}

              {/* Invitation & Password Setup Link Box */}
              {onboardActionLink && (
                <div
                  id="onboard-invitation-link-box"
                  data-testid="onboard-invitation-link-box"
                  className="p-4 bg-sky-50 border border-sky-200 rounded-xl space-y-2 shadow-2xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sky-950 text-xs flex items-center gap-1.5">
                      <KeyRound size={15} className="text-sky-600" />
                      Doctor Invitation & Password Setup Link
                    </span>
                    <span className="text-[10px] font-bold bg-sky-200 text-sky-900 px-2 py-0.5 rounded-full">
                      Ready to Deliver
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-600 leading-relaxed">
                    A secure password-setup link has been generated via Supabase Auth. Provide this link to the physician to complete initial password setup:
                  </p>
                  <div className="flex items-center gap-2 pt-1">
                    <input
                      readOnly
                      id="onboard-action-link-input"
                      data-testid="onboard-action-link-input"
                      value={onboardActionLink}
                      className="flex-1 bg-white border border-slate-300 text-slate-800 px-2.5 py-1.5 rounded-lg text-[11px] font-mono select-all focus:outline-none"
                    />
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => {
                        navigator.clipboard.writeText(onboardActionLink);
                        setCopiedLink(true);
                        setTimeout(() => setCopiedLink(false), 2000);
                      }}
                      className="text-xs bg-sky-700 hover:bg-sky-800 text-white font-semibold shrink-0 gap-1"
                    >
                      {copiedLink ? (
                        <>
                          <Check size={12} />
                          Copied!
                        </>
                      ) : (
                        <>
                          <Copy size={12} />
                          Copy Link
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}

              {/* Client Validation Errors Summary */}
              {Object.keys(validationErrors).length > 0 && (
                <div
                  id="onboard-validation-summary"
                  data-testid="onboard-validation-summary"
                  className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-800 space-y-1 shadow-2xs"
                >
                  <div className="flex items-center gap-2 font-bold text-xs text-amber-900">
                    <AlertCircle size={15} className="text-amber-600" />
                    <span>Please correct the following fields before proceeding:</span>
                  </div>
                  <ul className="list-disc list-inside space-y-0.5 pl-4 text-[11px] text-amber-700">
                    {Object.values(validationErrors).map((msg, i) => (
                      <li key={i}>{msg}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 1. Identity & Credentials */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    1. Professional Identity & Contact
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-semibold text-slate-700">
                      Full Physician Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="onboard-fullname-input"
                      data-testid="onboard-fullname-input"
                      type="text"
                      required
                      placeholder="e.g. Dr. Arthur Conan, MD"
                      value={onboardFullName}
                      onChange={(e) => setOnboardFullName(e.target.value)}
                      className={cn(
                        "w-full px-3 py-2 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                        validationErrors.fullName ? "border-rose-300 bg-rose-50/30" : "border-slate-300"
                      )}
                    />
                    {validationErrors.fullName && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.fullName}</span>
                    )}
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700">
                      Professional Email <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="onboard-email-input"
                      data-testid="onboard-email-input"
                      type="email"
                      required
                      placeholder="physician@careroute.org"
                      value={onboardEmail}
                      onChange={(e) => setOnboardEmail(e.target.value)}
                      className={cn(
                        "w-full px-3 py-2 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                        validationErrors.email ? "border-rose-300 bg-rose-50/30" : "border-slate-300"
                      )}
                    />
                    {validationErrors.email && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.email}</span>
                    )}
                  </div>

                  {/* Password */}
                  <div className="space-y-1">
                    <label
                      htmlFor="onboard-password-input"
                      className="font-semibold text-slate-700 flex items-center justify-between"
                    >
                      <span>
                        Password <span className="text-rose-500">*</span>
                      </span>
                      <span className="text-[10px] text-slate-400 font-normal">Min. 8 characters</span>
                    </label>
                    <div className="relative">
                      <input
                        id="onboard-password-input"
                        data-testid="onboard-password-input"
                        type={showOnboardPassword ? "text" : "password"}
                        required
                        placeholder="••••••••"
                        value={onboardPassword}
                        onChange={(e) => setOnboardPassword(e.target.value)}
                        className={cn(
                          "w-full px-3 py-2 pr-10 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                          validationErrors.password ? "border-rose-300 bg-rose-50/30" : "border-slate-300"
                        )}
                        aria-invalid={Boolean(validationErrors.password)}
                        aria-describedby={validationErrors.password ? "onboard-password-error" : undefined}
                      />
                      <button
                        type="button"
                        id="toggle-onboard-password-btn"
                        data-testid="toggle-onboard-password-btn"
                        onClick={() => setShowOnboardPassword(!showOnboardPassword)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors p-1"
                        aria-label={showOnboardPassword ? "Hide password" : "Show password"}
                      >
                        {showOnboardPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {validationErrors.password && (
                      <span id="onboard-password-error" className="text-[10px] text-rose-600 block">
                        {validationErrors.password}
                      </span>
                    )}
                  </div>

                  {/* Confirm Password */}
                  <div className="space-y-1">
                    <label
                      htmlFor="onboard-confirm-password-input"
                      className="font-semibold text-slate-700"
                    >
                      Confirm Password <span className="text-rose-500">*</span>
                    </label>
                    <div className="relative">
                      <input
                        id="onboard-confirm-password-input"
                        data-testid="onboard-confirm-password-input"
                        type={showOnboardConfirmPassword ? "text" : "password"}
                        required
                        placeholder="••••••••"
                        value={onboardConfirmPassword}
                        onChange={(e) => setOnboardConfirmPassword(e.target.value)}
                        className={cn(
                          "w-full px-3 py-2 pr-10 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                          validationErrors.confirmPassword ? "border-rose-300 bg-rose-50/30" : "border-slate-300"
                        )}
                        aria-invalid={Boolean(validationErrors.confirmPassword)}
                        aria-describedby={validationErrors.confirmPassword ? "onboard-confirm-password-error" : undefined}
                      />
                      <button
                        type="button"
                        id="toggle-onboard-confirm-password-btn"
                        data-testid="toggle-onboard-confirm-password-btn"
                        onClick={() => setShowOnboardConfirmPassword(!showOnboardConfirmPassword)}
                        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 transition-colors p-1"
                        aria-label={showOnboardConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                      >
                        {showOnboardConfirmPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                    </div>
                    {validationErrors.confirmPassword && (
                      <span id="onboard-confirm-password-error" className="text-[10px] text-rose-600 block">
                        {validationErrors.confirmPassword}
                      </span>
                    )}
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700">
                      Medical License No. <span className="text-rose-500">*</span>
                    </label>
                    <input
                      id="onboard-license-input"
                      data-testid="onboard-license-input"
                      type="text"
                      required
                      placeholder="e.g. MD-98241"
                      value={onboardLicense}
                      onChange={(e) => setOnboardLicense(e.target.value)}
                      className={cn(
                        "w-full px-3 py-2 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                        validationErrors.license ? "border-rose-300 bg-rose-50/30" : "border-slate-300"
                      )}
                    />
                    {validationErrors.license && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.license}</span>
                    )}
                  </div>

                  <div className="sm:col-span-2 space-y-1">
                    <label className="font-semibold text-slate-700 flex items-center gap-1.5">
                      <Phone size={13} className="text-slate-400" />
                      Contact Phone Number <span className="text-slate-400 font-normal">(Optional)</span>
                    </label>
                    <input
                      id="onboard-phone-input"
                      data-testid="onboard-phone-input"
                      type="tel"
                      placeholder="e.g. +1 555-019-2834"
                      value={onboardPhone}
                      onChange={(e) => setOnboardPhone(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </div>
                </div>
              </div>

              {/* 2. Facility & Department Affiliation */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    2. Hospital Facility & Department Assignment
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {/* Hospital Selector */}
                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700 flex items-center justify-between">
                      <span>Hospital Facility <span className="text-rose-500">*</span></span>
                      {isTenantRestricted && (
                        <span className="text-[10px] font-semibold text-amber-700 flex items-center gap-1">
                          <Lock size={10} />
                          Tenant Locked
                        </span>
                      )}
                    </label>

                    {isTenantRestricted ? (
                      <div
                        id="onboard-hospital-locked"
                        data-testid="onboard-hospital-locked"
                        className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between"
                      >
                        <div className="flex items-center gap-2">
                          <div className="p-1 rounded bg-amber-100 text-amber-800">
                            <Lock size={13} />
                          </div>
                          <div>
                            <span className="font-bold text-slate-800 text-xs block">
                              {currentHospital?.name || user?.hospital_id}
                            </span>
                            <span className="text-[10px] text-slate-500 font-mono">
                              ID: {user?.hospital_id}
                            </span>
                          </div>
                        </div>
                        <span className="text-[10px] font-semibold uppercase bg-amber-50 text-amber-800 border border-amber-200 px-2 py-0.5 rounded-full">
                          Restricted
                        </span>
                      </div>
                    ) : (
                      <div>
                        <select
                          id="onboard-hospital-select"
                          data-testid="onboard-hospital-select"
                          value={onboardHospitalId}
                          onChange={(e) => setOnboardHospitalId(e.target.value)}
                          disabled={isLoadingLookups}
                          className={cn(
                            "w-full px-3 py-2 rounded-lg border text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-sky-500",
                            validationErrors.hospital ? "border-rose-300" : "border-slate-300"
                          )}
                        >
                          <option value="">-- Select Hospital Facility --</option>
                          {hospitals.map((h) => (
                            <option key={h.id} value={h.id}>
                              {h.name} ({h.code})
                            </option>
                          ))}
                        </select>
                        {hospitals.length === 0 && !isLoadingLookups && (
                          <span className="text-[10px] text-amber-600 block mt-1">
                            No hospital facilities found in database.
                          </span>
                        )}
                      </div>
                    )}

                    {validationErrors.hospital && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.hospital}</span>
                    )}
                  </div>

                  {/* Department Selector */}
                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700 flex items-center justify-between">
                      <span>Clinical Department <span className="text-slate-400 font-normal">(Optional)</span></span>
                      {isLoadingDepartments && (
                        <span className="text-[10px] text-sky-600 flex items-center gap-1">
                          <Loader2 size={10} className="animate-spin" />
                          Loading...
                        </span>
                      )}
                    </label>

                    <select
                      id="onboard-department-select"
                      data-testid="onboard-department-select"
                      value={onboardDepartmentId}
                      onChange={(e) => setOnboardDepartmentId(e.target.value)}
                      disabled={isLoadingDepartments || !effectiveHospitalId}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-sky-500 disabled:bg-slate-50 disabled:text-slate-400"
                    >
                      <option value="">-- Select Department (Optional) --</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name} ({d.code})
                        </option>
                      ))}
                    </select>

                    {!effectiveHospitalId ? (
                      <span className="text-[10px] text-slate-400 block">
                        Select a hospital to view associated departments.
                      </span>
                    ) : !isLoadingDepartments && departments.length === 0 ? (
                      <span className="text-[10px] text-slate-400 block italic">
                        No active departments found for this hospital facility.
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>

              {/* 3. Clinical Specialties Multi-Select & Primary Designation */}
              <div className="space-y-3">
                <div className="flex items-center justify-between pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    3. Clinical Specialties & Primary Designation
                  </span>
                  <span className="text-[11px] font-semibold text-sky-700">
                    {onboardSpecialtyIds.length} selected
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="relative">
                    <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                    <input
                      id="onboard-specialty-search"
                      data-testid="onboard-specialty-search"
                      type="text"
                      placeholder="Search specialties (e.g. Cardiology, Neurology, Pediatrics)..."
                      value={specialtySearch}
                      onChange={(e) => setSpecialtySearch(e.target.value)}
                      className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                  </div>

                  <div
                    id="onboard-specialties-container"
                    data-testid="onboard-specialties-container"
                    className="border border-slate-200 rounded-xl p-3 max-h-48 overflow-y-auto space-y-1.5 bg-slate-50/50"
                  >
                    {isLoadingLookups ? (
                      <div className="py-6 text-center text-slate-400 flex items-center justify-center gap-2">
                        <Loader2 size={16} className="animate-spin text-sky-600" />
                        <span>Loading clinical specialties...</span>
                      </div>
                    ) : specialties.length === 0 ? (
                      <div className="py-6 text-center text-slate-400 italic">
                        No clinical specialties found in the database.
                      </div>
                    ) : filteredSpecialties.length === 0 ? (
                      <div className="py-6 text-center text-slate-400 italic">
                        No specialties match &ldquo;{specialtySearch}&rdquo;.
                      </div>
                    ) : (
                      filteredSpecialties.map((spec) => {
                        const isSelected = onboardSpecialtyIds.includes(spec.id);
                        const isPrimary = onboardPrimarySpecialtyId === spec.id;

                        return (
                          <div
                            key={spec.id}
                            className={cn(
                              "flex items-center justify-between p-2 rounded-lg border transition-colors",
                              isSelected
                                ? isPrimary
                                  ? "bg-amber-50/70 border-amber-300"
                                  : "bg-white border-sky-200"
                                : "bg-white border-slate-200 hover:border-slate-300"
                            )}
                          >
                            <label
                              htmlFor={`spec-checkbox-${spec.id}`}
                              className="flex items-center gap-2.5 cursor-pointer flex-1"
                            >
                              <input
                                id={`spec-checkbox-${spec.id}`}
                                data-testid={`spec-checkbox-${spec.id}`}
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => handleToggleSpecialty(spec.id)}
                                className="h-4 w-4 rounded border-slate-300 text-sky-600 focus:ring-sky-500 cursor-pointer"
                              />
                              <div>
                                <span className="font-semibold text-slate-800 text-xs block">
                                  {spec.name}
                                </span>
                                <span className="text-[10px] text-slate-400 font-mono">
                                  {spec.code}
                                </span>
                              </div>
                            </label>

                            {isSelected && (
                              <div className="flex items-center gap-1.5 pl-2 shrink-0">
                                {isPrimary ? (
                                  <span
                                    id={`primary-badge-${spec.id}`}
                                    data-testid={`primary-badge-${spec.id}`}
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 shadow-2xs"
                                  >
                                    <Star size={10} className="fill-amber-500 text-amber-600" />
                                    Primary Specialty
                                  </span>
                                ) : (
                                  <button
                                    id={`set-primary-btn-${spec.id}`}
                                    data-testid={`set-primary-btn-${spec.id}`}
                                    type="button"
                                    onClick={() => handleSetPrimarySpecialty(spec.id)}
                                    className="text-[10px] font-semibold text-slate-600 hover:text-amber-800 hover:bg-amber-50 border border-slate-200 hover:border-amber-300 px-2 py-0.5 rounded-md flex items-center gap-1 transition-colors"
                                  >
                                    <Star size={10} className="text-slate-400" />
                                    Make Primary
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>

                  {onboardSpecialtyIds.length > 0 && (
                    <div className="flex items-center justify-between text-[11px] pt-1">
                      <span className="text-slate-500">
                        Primary Specialty:{" "}
                        <strong className="text-slate-800">
                          {specialties.find((s) => s.id === onboardPrimarySpecialtyId)?.name ||
                            "None designated"}
                        </strong>
                      </span>
                      {onboardPrimarySpecialtyId ? (
                        <span className="text-emerald-600 font-medium flex items-center gap-1">
                          <CheckCircle2 size={12} />
                          Primary designated
                        </span>
                      ) : (
                        <span className="text-amber-600 font-semibold">
                          * Please click &ldquo;Make Primary&rdquo; for one specialty
                        </span>
                      )}
                    </div>
                  )}

                  {validationErrors.primarySpecialty && (
                    <span className="text-[10px] text-rose-600 block">
                      {validationErrors.primarySpecialty}
                    </span>
                  )}
                </div>
              </div>

              {/* 4. Clinical Practice & Availability */}
              <div className="space-y-3">
                <div className="flex items-center gap-2 pb-1 border-b border-slate-100">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                    4. Practice Configuration
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700">Years Experience</label>
                    <input
                      id="onboard-experience-input"
                      data-testid="onboard-experience-input"
                      type="number"
                      min="0"
                      max="60"
                      value={onboardExperience}
                      onChange={(e) => setOnboardExperience(parseInt(e.target.value) || 0)}
                      className={cn(
                        "w-full px-3 py-2 rounded-lg border text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500",
                        validationErrors.experience ? "border-rose-300" : "border-slate-300"
                      )}
                    />
                    {validationErrors.experience && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.experience}</span>
                    )}
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700">Consultation Mode</label>
                    <select
                      id="onboard-mode-select"
                      data-testid="onboard-mode-select"
                      value={onboardMode}
                      onChange={(e) => setOnboardMode(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-sky-500"
                    >
                      <option value="both">Both (In-Person & Video)</option>
                      <option value="in_person">In-Person Only</option>
                      <option value="video">Video Only</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700">Languages (e.g. en, es)</label>
                    <input
                      id="onboard-languages-input"
                      data-testid="onboard-languages-input"
                      type="text"
                      value={onboardLanguages}
                      onChange={(e) => setOnboardLanguages(e.target.value)}
                      placeholder="en, es, hi"
                      className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500"
                    />
                    {validationErrors.languages && (
                      <span className="text-[10px] text-rose-600 block">{validationErrors.languages}</span>
                    )}
                  </div>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
                <Button
                  id="cancel-onboard-doctor-btn"
                  data-testid="cancel-onboard-doctor-btn"
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleCloseModal}
                  disabled={isOnboardSubmitting}
                >
                  {onboardActionLink ? "Done / Close" : "Cancel"}
                </Button>
                {!onboardActionLink && (
                  <Button
                    id="confirm-onboard-doctor-btn"
                    data-testid="confirm-onboard-doctor-btn"
                    type="submit"
                    size="sm"
                    className="bg-sky-700 hover:bg-sky-800 text-white font-semibold gap-1.5"
                    isLoading={isOnboardSubmitting}
                    disabled={isOnboardSubmitting}
                  >
                    {isOnboardSubmitting ? (
                      <>
                        <Loader2 size={14} className="animate-spin" />
                        Provisioning Physician...
                      </>
                    ) : (
                      "Onboard Physician"
                    )}
                  </Button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Deactivate / Reactivate Status Modal */}
      {statusModalOpen && selectedDoctorForStatus && (
        <div
          id="doctor-status-modal"
          data-testid="doctor-status-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95">
            <div
              className={cn(
                "px-6 py-4 text-white flex items-center justify-between border-b",
                selectedDoctorForStatus.is_active
                  ? "bg-amber-900 border-amber-950"
                  : "bg-emerald-900 border-emerald-950"
              )}
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={cn(
                    "p-2 rounded-xl text-white",
                    selectedDoctorForStatus.is_active ? "bg-amber-700" : "bg-emerald-700"
                  )}
                >
                  {selectedDoctorForStatus.is_active ? <UserX size={18} /> : <UserCheck size={18} />}
                </div>
                <div>
                  <h3 className="font-bold text-sm text-white">
                    {selectedDoctorForStatus.is_active ? "Deactivate Physician Account" : "Reactivate Physician Account"}
                  </h3>
                  <p className="text-[11px] text-slate-300">
                    {selectedDoctorForStatus.profile?.full_name} ({selectedDoctorForStatus.license_number})
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setStatusModalOpen(false)}
                disabled={isStatusSubmitting}
                className="text-slate-300 hover:text-white p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            <form onSubmit={handleUpdateDoctorStatus} className="p-6 space-y-4 text-xs">
              {statusModalError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-700 flex items-start gap-2">
                  <AlertCircle size={15} className="text-rose-500 shrink-0 mt-0.5" />
                  <span>{statusModalError}</span>
                </div>
              )}

              {selectedDoctorForStatus.is_active ? (
                <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 space-y-1.5 leading-relaxed">
                  <div className="flex items-center gap-1.5 font-bold text-amber-950">
                    <AlertTriangle size={15} className="text-amber-600" />
                    <span>Deactivation Impact</span>
                  </div>
                  <p className="text-[11px] text-amber-800">
                    Deactivating will immediately deny future logins, revoke protected doctor endpoints, and block new outpatient appointments.
                  </p>
                  <p className="text-[11px] font-semibold text-emerald-800 flex items-center gap-1">
                    <ShieldCheck size={12} />
                    All historical appointments, queues, and consultation records are preserved.
                  </p>
                </div>
              ) : (
                <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-900 space-y-1.5 leading-relaxed">
                  <div className="flex items-center gap-1.5 font-bold text-emerald-950">
                    <CheckCircle2 size={15} className="text-emerald-600" />
                    <span>Reactivation Impact</span>
                  </div>
                  <p className="text-[11px] text-emerald-800">
                    Reactivating this physician will restore login access and re-enable clinical appointment scheduling.
                  </p>
                </div>
              )}

              <div className="space-y-1">
                <label className="font-semibold text-slate-700">Administrative Rationale (Optional)</label>
                <input
                  id="status-modal-reason-input"
                  data-testid="status-modal-reason-input"
                  type="text"
                  placeholder="e.g. Sabbatical, medical leave, or scheduled roster rotation"
                  value={statusModalReason}
                  onChange={(e) => setStatusModalReason(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-sky-500 text-xs"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setStatusModalOpen(false)}
                  disabled={isStatusSubmitting}
                >
                  Cancel
                </Button>
                <Button
                  id="confirm-doctor-status-btn"
                  data-testid="confirm-doctor-status-btn"
                  type="submit"
                  size="sm"
                  isLoading={isStatusSubmitting}
                  className={cn(
                    "text-white font-semibold",
                    selectedDoctorForStatus.is_active
                      ? "bg-amber-600 hover:bg-amber-700"
                      : "bg-emerald-600 hover:bg-emerald-700"
                  )}
                >
                  {selectedDoctorForStatus.is_active ? "Confirm Deactivation" : "Confirm Reactivation"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Doctor Modal Dialog */}
      {deleteModalOpen && selectedDoctorForDelete && (
        <div
          id="doctor-delete-modal"
          data-testid="doctor-delete-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95">
            <div className="bg-rose-950 px-6 py-4 text-white flex items-center justify-between border-b border-rose-900">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-rose-700 text-white">
                  <Trash2 size={18} />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-white">Delete Physician Record</h3>
                  <p className="text-[11px] text-slate-300">
                    {selectedDoctorForDelete.profile?.full_name} ({selectedDoctorForDelete.license_number})
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDeleteModalOpen(false)}
                disabled={isDeleteSubmitting}
                className="text-slate-300 hover:text-white p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4 text-xs">
              {deleteModalError ? (
                <div className="p-3.5 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 space-y-2 leading-relaxed">
                  <div className="flex items-center gap-1.5 font-bold text-rose-950">
                    <AlertCircle size={16} className="text-rose-600 shrink-0" />
                    <span>Permanent Deletion Blocked</span>
                  </div>
                  <p className="text-[11px] text-rose-700">{deleteModalError}</p>
                  {deleteHasClinicalHistory && (
                    <div className="pt-2">
                      <Button
                        size="sm"
                        onClick={() => {
                          setDeleteModalOpen(false);
                          setSelectedDoctorForStatus(selectedDoctorForDelete);
                          setStatusModalReason("Deactivated due to clinical retention restrictions");
                          setStatusModalError(null);
                          setStatusModalOpen(true);
                        }}
                        className="w-full bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold"
                      >
                        Deactivate Physician Instead
                      </Button>
                    </div>
                  )}
                </div>
              ) : (
                <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 space-y-2 leading-relaxed">
                  <div className="flex items-center gap-1.5 font-bold text-amber-950">
                    <AlertTriangle size={15} className="text-amber-600" />
                    <span>Medical Retention & Audit Safeguard</span>
                  </div>
                  <p className="text-[11px] text-amber-800">
                    Permanent deletion is permitted <strong>only</strong> if this physician has zero appointments, consultations, and queue records. If any dependent clinical records exist, deletion is prohibited and deactivation must be used instead.
                  </p>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setDeleteModalOpen(false)}
                  disabled={isDeleteSubmitting}
                >
                  Cancel
                </Button>
                {!deleteHasClinicalHistory && (
                  <Button
                    id="confirm-delete-doctor-btn"
                    data-testid="confirm-delete-doctor-btn"
                    type="button"
                    size="sm"
                    onClick={handleDeleteDoctor}
                    isLoading={isDeleteSubmitting}
                    className="bg-rose-700 hover:bg-rose-800 text-white font-semibold"
                  >
                    Permanently Delete Record
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Resend Invitation / Link Modal */}
      {resendModalOpen && selectedDoctorForResend && (
        <div
          id="resend-invite-modal"
          data-testid="resend-invite-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-500 rounded-lg text-white">
                  <KeyRound size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Physician Invitation & Credentials</h3>
                  <p className="text-[11px] text-slate-400">
                    Regenerate secure access credentials for {selectedDoctorForResend.profile?.full_name}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setResendModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <div className="bg-slate-50 p-3 rounded-xl border border-slate-200 text-xs space-y-1">
                <div className="flex justify-between">
                  <span className="text-slate-500">Physician Name:</span>
                  <span className="font-semibold text-slate-900">
                    {selectedDoctorForResend.profile?.full_name}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Email:</span>
                  <span className="font-semibold text-slate-900">
                    {selectedDoctorForResend.profile?.email}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">License Number:</span>
                  <span className="font-mono text-slate-700">
                    {selectedDoctorForResend.license_number}
                  </span>
                </div>
              </div>

              {resendLoading ? (
                <div className="p-8 text-center space-y-2">
                  <Loader2 size={24} className="animate-spin text-indigo-600 mx-auto" />
                  <p className="text-xs text-slate-500">
                    Regenerating secure invitation link via Supabase Auth...
                  </p>
                </div>
              ) : resendError ? (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-start gap-2">
                  <AlertCircle size={16} className="text-rose-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-semibold block">Failed to regenerate invitation:</span>
                    <span>{resendError}</span>
                  </div>
                </div>
              ) : resendActionLink ? (
                <div className="space-y-3">
                  <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800">
                    <p className="font-semibold">Invitation link successfully generated!</p>
                    <p className="text-[11px] text-emerald-700 mt-0.5">
                      Provide this secure link to the physician to allow them to configure their password and activate their clinical workspace.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Setup / Activation Link:
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        id="resend-action-link-input"
                        data-testid="resend-action-link-input"
                        type="text"
                        readOnly
                        value={resendActionLink}
                        className="flex-1 px-3 py-2 text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg text-slate-700 focus:outline-none"
                      />
                      <Button
                        id="copy-resend-link-btn"
                        data-testid="copy-resend-link-btn"
                        type="button"
                        size="sm"
                        onClick={() => {
                          if (resendActionLink && typeof navigator !== "undefined") {
                            navigator.clipboard.writeText(resendActionLink);
                            setCopiedResendLink(true);
                            setTimeout(() => setCopiedResendLink(false), 3000);
                          }
                        }}
                        className="gap-1.5 text-xs bg-indigo-700 hover:bg-indigo-800 text-white shrink-0"
                      >
                        {copiedResendLink ? (
                          <>
                            <Check size={14} />
                            Copied
                          </>
                        ) : (
                          <>
                            <Copy size={14} />
                            Copy Link
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="pt-2 flex justify-end border-t border-slate-100">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setResendModalOpen(false)}
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Doctor Schedule Management Modal */}
      {scheduleModalOpen && selectedDoctorForSchedule && (
        <div
          id="doctor-schedule-modal"
          data-testid="doctor-schedule-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white w-full max-w-xl rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-sky-600 rounded-lg text-white">
                  <Calendar size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Consultation Schedule & Hours</h3>
                  <p className="text-[11px] text-slate-400">
                    {selectedDoctorForSchedule.profile?.full_name} · {selectedDoctorForSchedule.hospital?.name || "Clinic Facility"}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setScheduleModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4">
              {scheduleModalError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-center gap-2">
                  <AlertCircle size={15} className="text-rose-600 shrink-0" />
                  <span>{scheduleModalError}</span>
                </div>
              )}

              {scheduleModalSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs flex items-center gap-2">
                  <CheckCircle2 size={15} className="text-emerald-600 shrink-0" />
                  <span>{scheduleModalSuccess}</span>
                </div>
              )}

              {isLoadingSchedules ? (
                <div className="p-8 text-center space-y-2">
                  <RotateCcw size={20} className="animate-spin text-sky-600 mx-auto" />
                  <p className="text-xs text-slate-500 font-medium">Loading consultation schedules...</p>
                </div>
              ) : (
                <>
                  {doctorSchedules.length === 0 ? (
                    <div className="p-6 text-center space-y-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900">
                      <Clock size={24} className="text-amber-600 mx-auto" />
                      <div className="space-y-1">
                        <p className="text-xs font-bold">No Consultation Schedules Configured</p>
                        <p className="text-[11px] text-amber-700 max-w-sm mx-auto">
                          This physician cannot currently receive patient bookings. You can initialize standard outpatient hours or configure custom schedule windows.
                        </p>
                      </div>
                      <Button
                        type="button"
                        size="sm"
                        onClick={handleInitializeDefaultSchedule}
                        disabled={isSavingSchedules}
                        className="bg-sky-700 hover:bg-sky-800 text-white text-xs gap-1.5"
                      >
                        <Calendar size={13} />
                        Initialize Default (Mon–Fri 09:00 - 17:00)
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                        <span className="text-xs font-semibold text-slate-700">Weekly Schedule Windows</span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={handleInitializeDefaultSchedule}
                          disabled={isSavingSchedules}
                          className="text-[11px] h-7 text-sky-700 hover:bg-sky-50 gap-1 font-semibold"
                        >
                          <RotateCcw size={12} />
                          Reset to Default Mon-Fri
                        </Button>
                      </div>

                      <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                        {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map(
                          (dayName, dayIdx) => {
                            const sched = doctorSchedules.find((s) => s.day_of_week === dayIdx);
                            const isActive = Boolean(sched && sched.is_active);

                            return (
                              <div
                                key={dayName}
                                className={`p-2.5 rounded-xl border text-xs flex items-center justify-between gap-3 ${
                                  isActive
                                    ? "bg-white border-slate-200"
                                    : "bg-slate-50 border-slate-100 opacity-60"
                                }`}
                              >
                                <div className="flex items-center gap-2 w-28 shrink-0">
                                  <input
                                    type="checkbox"
                                    checked={isActive}
                                    id={`check-day-${dayIdx}`}
                                    onChange={(e) => {
                                      const checked = e.target.checked;
                                      if (checked) {
                                        if (sched) {
                                          setDoctorSchedules((prev) =>
                                            prev.map((s) =>
                                              s.day_of_week === dayIdx ? { ...s, is_active: true } : s
                                            )
                                          );
                                        } else {
                                          setDoctorSchedules((prev) => [
                                            ...prev,
                                            {
                                              day_of_week: dayIdx,
                                              start_time: "09:00:00",
                                              end_time: "17:00:00",
                                              slot_duration_minutes: 30,
                                              is_active: true,
                                            },
                                          ]);
                                        }
                                      } else {
                                        setDoctorSchedules((prev) =>
                                          prev.filter((s) => s.day_of_week !== dayIdx)
                                        );
                                      }
                                    }}
                                    className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 h-3.5 w-3.5"
                                  />
                                  <label
                                    htmlFor={`check-day-${dayIdx}`}
                                    className="font-medium text-slate-800 cursor-pointer"
                                  >
                                    {dayName}
                                  </label>
                                </div>

                                {isActive && sched ? (
                                  <div className="flex items-center gap-2 grow justify-end">
                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] text-slate-400">Start:</span>
                                      <input
                                        type="time"
                                        value={sched.start_time.slice(0, 5)}
                                        onChange={(e) => {
                                          const val = e.target.value ? `${e.target.value}:00` : sched.start_time;
                                          setDoctorSchedules((prev) =>
                                            prev.map((s) =>
                                              s.day_of_week === dayIdx ? { ...s, start_time: val } : s
                                            )
                                          );
                                        }}
                                        className="px-1.5 py-0.5 border border-slate-200 rounded text-xs bg-white text-slate-800 font-mono"
                                      />
                                    </div>

                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] text-slate-400">End:</span>
                                      <input
                                        type="time"
                                        value={sched.end_time.slice(0, 5)}
                                        onChange={(e) => {
                                          const val = e.target.value ? `${e.target.value}:00` : sched.end_time;
                                          setDoctorSchedules((prev) =>
                                            prev.map((s) =>
                                              s.day_of_week === dayIdx ? { ...s, end_time: val } : s
                                            )
                                          );
                                        }}
                                        className="px-1.5 py-0.5 border border-slate-200 rounded text-xs bg-white text-slate-800 font-mono"
                                      />
                                    </div>

                                    <div className="flex items-center gap-1">
                                      <span className="text-[10px] text-slate-400">Slot:</span>
                                      <select
                                        value={sched.slot_duration_minutes}
                                        onChange={(e) => {
                                          const val = parseInt(e.target.value, 10);
                                          setDoctorSchedules((prev) =>
                                            prev.map((s) =>
                                              s.day_of_week === dayIdx
                                                ? { ...s, slot_duration_minutes: val }
                                                : s
                                            )
                                          );
                                        }}
                                        className="px-1.5 py-0.5 border border-slate-200 rounded text-xs bg-white text-slate-800"
                                      >
                                        <option value={15}>15m</option>
                                        <option value={20}>20m</option>
                                        <option value={30}>30m</option>
                                        <option value={45}>45m</option>
                                        <option value={60}>60m</option>
                                      </select>
                                    </div>
                                  </div>
                                ) : (
                                  <span className="text-[11px] text-slate-400 italic">Not scheduled</span>
                                )}
                              </div>
                            );
                          }
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}

              <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setScheduleModalOpen(false)}
                >
                  Close
                </Button>
                {doctorSchedules.length > 0 && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleSaveSchedules}
                    disabled={isSavingSchedules || isLoadingSchedules}
                    className="bg-sky-700 hover:bg-sky-800 text-white font-semibold text-xs gap-1.5"
                  >
                    {isSavingSchedules ? "Saving..." : "Save Schedules"}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Repair Unscheduled Doctors Modal */}
      {repairModalOpen && (
        <div
          id="repair-schedules-modal"
          data-testid="repair-schedules-modal"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4 animate-in fade-in"
        >
          <div className="bg-white w-full max-w-lg rounded-2xl shadow-2xl border border-slate-200 overflow-hidden flex flex-col max-h-[90vh]">
            <div className="px-6 py-4 bg-indigo-900 text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-700 rounded-lg text-white">
                  <Calendar size={16} />
                </div>
                <div>
                  <h3 className="text-sm font-bold">Repair Physician Schedules</h3>
                  <p className="text-[11px] text-indigo-200">
                    Inspect and safely configure default outpatient consultation hours
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setRepairModalOpen(false)}
                className="text-indigo-300 hover:text-white"
              >
                <X size={18} />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-4">
              {repairError && (
                <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-center gap-2">
                  <AlertCircle size={15} className="text-rose-600 shrink-0" />
                  <span>{repairError}</span>
                </div>
              )}

              {repairSuccess && (
                <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs flex items-center gap-2">
                  <CheckCircle2 size={15} className="text-emerald-600 shrink-0" />
                  <span>{repairSuccess}</span>
                </div>
              )}

              {repairLoading ? (
                <div className="p-8 text-center space-y-2">
                  <RotateCcw size={20} className="animate-spin text-indigo-600 mx-auto" />
                  <p className="text-xs text-slate-500 font-medium">Scanning registered physicians...</p>
                </div>
              ) : repairDryRunData ? (
                <div className="space-y-3">
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1">
                    <div className="flex justify-between">
                      <span className="text-slate-500">Unscheduled Physicians Found:</span>
                      <span className="font-bold text-slate-900">{repairDryRunData.unscheduled_count}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 pt-1">
                      Safe & Idempotent: Only doctors lacking active schedules will be configured with default hours (Monday–Friday 09:00 - 17:00, 30m slots). Existing schedules, appointments, and patients are never altered.
                    </p>
                  </div>

                  {repairDryRunData.unscheduled_count > 0 ? (
                    <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                      <p className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide">
                        Physicians to be configured:
                      </p>
                      {repairDryRunData.doctors.map((d) => (
                        <div
                          key={d.doctor_id}
                          className="p-2 rounded-lg bg-white border border-slate-200 text-xs flex items-center justify-between"
                        >
                          <span className="font-semibold text-slate-800">Dr. {d.doctor_name}</span>
                          <span className="text-[10px] text-slate-400 font-mono">{d.doctor_id.slice(0, 8)}...</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-4 text-center text-xs text-emerald-700 bg-emerald-50 border border-emerald-100 rounded-xl font-medium">
                      All registered active physicians already have configured consultation schedules!
                    </div>
                  )}
                </div>
              ) : null}

              <div className="pt-3 flex items-center justify-end gap-2 border-t border-slate-100">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setRepairModalOpen(false)}
                >
                  Close
                </Button>
                {repairDryRunData && repairDryRunData.unscheduled_count > 0 && !repairSuccess && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={handleExecuteRepair}
                    disabled={repairLoading}
                    className="bg-indigo-700 hover:bg-indigo-800 text-white font-semibold text-xs gap-1.5"
                  >
                    {repairLoading ? "Repairing..." : `Execute Repair (${repairDryRunData.unscheduled_count})`}
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
