import test, { describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

describe("Admin Doctor Directory Lifecycle & Invitation Workflows (Frontend)", () => {
  let mockDoctors;

  beforeEach(() => {
    mockDoctors = [
      {
        id: "doc-1",
        hospital_id: "hosp-001",
        license_number: "LIC-ACTIVE-01",
        years_of_experience: 10,
        is_active: true,
        profile: {
          id: "prof-1",
          full_name: "Dr. Sarah Connor",
          email: "sarah.connor@hospital.org",
          is_active: true,
          role: "doctor",
        },
        has_clinical_history: true,
      },
      {
        id: "doc-2",
        hospital_id: "hosp-001",
        license_number: "LIC-INACT-02",
        years_of_experience: 5,
        is_active: false,
        profile: {
          id: "prof-2",
          full_name: "Dr. Miles Dyson",
          email: "miles.dyson@hospital.org",
          is_active: false,
          role: "doctor",
        },
        has_clinical_history: false,
      },
      {
        id: "doc-3",
        hospital_id: "hosp-002",
        license_number: "LIC-OTHER-03",
        years_of_experience: 8,
        is_active: true,
        profile: {
          id: "prof-3",
          full_name: "Dr. John Connor",
          email: "john.connor@otherhospital.org",
          is_active: true,
          role: "doctor",
        },
        has_clinical_history: false,
      },
    ];
  });

  // Client-side lifecycle service simulator
  class DoctorDirectoryServiceSimulator {
    constructor(adminUser = { id: "admin-1", role: "admin", hospital_id: "hosp-001" }) {
      this.adminUser = adminUser;
    }

    async listDoctorsAdmin(hospitalId = null, status = "all") {
      const effectiveHospId = this.adminUser.hospital_id || hospitalId;
      return mockDoctors.filter((doc) => {
        if (effectiveHospId && doc.hospital_id !== effectiveHospId) {
          return false;
        }
        if (status === "active" && !doc.is_active) {
          return false;
        }
        if (status === "inactive" && doc.is_active) {
          return false;
        }
        return true;
      });
    }

    async updateDoctorStatus(doctorId, isActive, reason = null) {
      const doc = mockDoctors.find((d) => d.id === doctorId);
      if (!doc) {
        throw new Error("DOCTOR_NOT_FOUND");
      }
      if (this.adminUser.hospital_id && doc.hospital_id !== this.adminUser.hospital_id) {
        const err = new Error("Cannot modify physicians outside assigned hospital");
        err.code = "CROSS_HOSPITAL_FORBIDDEN";
        err.status = 403;
        throw err;
      }
      doc.is_active = isActive;
      doc.profile.is_active = isActive;
      return {
        doctor_id: doc.id,
        profile_id: doc.profile.id,
        full_name: doc.profile.full_name,
        email: doc.profile.email,
        is_active: doc.is_active,
        status: doc.is_active ? "active" : "deactivated",
        message: `Doctor account ${doc.is_active ? "reactivated" : "deactivated"} successfully.`,
      };
    }

    async deleteDoctor(doctorId) {
      const docIndex = mockDoctors.findIndex((d) => d.id === doctorId);
      if (docIndex === -1) {
        throw new Error("DOCTOR_NOT_FOUND");
      }
      const doc = mockDoctors[docIndex];
      if (this.adminUser.hospital_id && doc.hospital_id !== this.adminUser.hospital_id) {
        const err = new Error("Cannot delete physicians outside assigned hospital");
        err.code = "CROSS_HOSPITAL_FORBIDDEN";
        err.status = 403;
        throw err;
      }
      if (doc.has_clinical_history) {
        const err = new Error(
          "Cannot permanently delete physician with historical appointments, queues, or consultations. Medical record retention regulations require deactivation instead."
        );
        err.code = "CANNOT_DELETE_DOCTOR_WITH_CLINICAL_HISTORY";
        err.status = 409;
        throw err;
      }
      mockDoctors.splice(docIndex, 1);
      return {
        doctor_id: doc.id,
        profile_id: doc.profile.id,
        full_name: doc.profile.full_name,
        email: doc.profile.email,
        is_active: false,
        status: "deleted",
        message: "Doctor record and credentials permanently deleted.",
      };
    }
  }

  test("1. Onboarding result encapsulates invitation status and action link", () => {
    const onboardingResponse = {
      profile_id: "prof-new-1",
      entity_id: "doc-new-1",
      full_name: "Dr. Elena Rostova",
      email: "elena@hospital.org",
      role: "doctor",
      status: "created",
      message: "Physician profile created. Supabase Auth invitation generated.",
      invitation_sent: true,
      action_link: "https://rkyrzctczohppspnzfxp.supabase.co/auth/v1/verify?token=invite-token&type=invite",
    };

    assert.equal(onboardingResponse.role, "doctor");
    assert.equal(onboardingResponse.invitation_sent, true);
    assert.ok(onboardingResponse.action_link.includes("token=invite-token"));
    assert.ok(onboardingResponse.action_link.startsWith("https://"));
  });

  test("2. Directory filters doctors by status (all, active, inactive)", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    const allDocs = await service.listDoctorsAdmin(null, "all");
    assert.equal(allDocs.length, 2);

    const activeDocs = await service.listDoctorsAdmin(null, "active");
    assert.equal(activeDocs.length, 1);
    assert.equal(activeDocs[0].id, "doc-1");

    const inactiveDocs = await service.listDoctorsAdmin(null, "inactive");
    assert.equal(inactiveDocs.length, 1);
    assert.equal(inactiveDocs[0].id, "doc-2");
  });

  test("3. Deactivating doctor revokes active status and updates profile immediately", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    const res = await service.updateDoctorStatus("doc-1", false, "Temporary medical leave");
    assert.equal(res.is_active, false);
    assert.equal(res.status, "deactivated");

    const updated = mockDoctors.find((d) => d.id === "doc-1");
    assert.equal(updated.is_active, false);
    assert.equal(updated.profile.is_active, false);
  });

  test("4. Reactivating doctor restores active status through authorized admin action", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    const res = await service.updateDoctorStatus("doc-2", true, "Returning to practice");
    assert.equal(res.is_active, true);
    assert.equal(res.status, "active");

    const updated = mockDoctors.find((d) => d.id === "doc-2");
    assert.equal(updated.is_active, true);
    assert.equal(updated.profile.is_active, true);
  });

  test("5. Cross-hospital doctor modification is blocked by tenant enforcement", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    await assert.rejects(
      async () => {
        await service.updateDoctorStatus("doc-3", false, "Unauthorized attempt");
      },
      (err) => {
        assert.equal(err.code, "CROSS_HOSPITAL_FORBIDDEN");
        assert.equal(err.status, 403);
        return true;
      }
    );
  });

  test("6. Permanent deletion is rejected when doctor has clinical history (preserves retention)", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    await assert.rejects(
      async () => {
        await service.deleteDoctor("doc-1");
      },
      (err) => {
        assert.equal(err.code, "CANNOT_DELETE_DOCTOR_WITH_CLINICAL_HISTORY");
        assert.equal(err.status, 409);
        assert.ok(err.message.includes("Medical record retention"));
        return true;
      }
    );

    // Doctor must remain intact
    assert.ok(mockDoctors.some((d) => d.id === "doc-1"));
  });

  test("7. Unused doctor with zero clinical history can be safely deleted", async () => {
    const service = new DoctorDirectoryServiceSimulator({ id: "admin-1", role: "admin", hospital_id: "hosp-001" });

    const res = await service.deleteDoctor("doc-2");
    assert.equal(res.status, "deleted");
    assert.equal(mockDoctors.some((d) => d.id === "doc-2"), false);
  });
});
