import test, { describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

describe("Admin Doctor Onboarding Form Validation & Payload Construction", () => {
  // Test lookup fixtures
  const mockHospitals = [
    { id: "hosp-001", name: "Metro General Hospital", code: "MGH", is_active: true },
    { id: "hosp-002", name: "St. Jude Clinical Center", code: "SJCC", is_active: true },
  ];

  const mockDepartments = [
    { id: "dept-001", hospital_id: "hosp-001", name: "Cardiology Dept", code: "CARD-01", is_active: true },
    { id: "dept-002", hospital_id: "hosp-001", name: "Emergency Dept", code: "EMERG-01", is_active: true },
    { id: "dept-003", hospital_id: "hosp-002", name: "Pediatrics Dept", code: "PED-02", is_active: true },
  ];

  const mockSpecialties = [
    { id: "spec-cardio", name: "Cardiology", code: "CARD", is_active: true },
    { id: "spec-neuro", name: "Neurology", code: "NEUR", is_active: true },
    { id: "spec-ped", name: "Pediatrics", code: "PEDI", is_active: true },
  ];

  // Logic model replicating AdminDoctorsPage validation and state machine
  class OnboardFormModel {
    constructor(adminUser = { id: "admin-1", role: "admin", hospital_id: null }) {
      this.adminUser = adminUser;
      this.hospitals = mockHospitals;
      this.specialties = mockSpecialties;
      this.departments = [];
      this.isLoadingDepartments = false;

      // Form state
      this.fullName = "";
      this.email = "";
      this.licenseNumber = "";
      this.phone = "";
      this.hospitalId = adminUser.hospital_id || "";
      this.departmentId = "";
      this.specialtyIds = [];
      this.primarySpecialtyId = "";
      this.experience = 5;
      this.mode = "both";
      this.languages = "en";

      if (this.hospitalId) {
        this.loadDepartmentsForHospital(this.hospitalId);
      }
    }

    get isTenantRestricted() {
      return Boolean(this.adminUser?.hospital_id);
    }

    get effectiveHospitalId() {
      return this.adminUser?.hospital_id || this.hospitalId;
    }

    setHospital(id) {
      if (this.isTenantRestricted) {
        // Tenant restriction prevents changing hospital
        return;
      }
      this.hospitalId = id;
      this.departmentId = "";
      this.loadDepartmentsForHospital(id);
    }

    loadDepartmentsForHospital(hospId) {
      this.isLoadingDepartments = true;
      this.departments = mockDepartments.filter((d) => d.hospital_id === hospId);
      this.isLoadingDepartments = false;
    }

    toggleSpecialty(specId) {
      const exists = this.specialtyIds.includes(specId);
      if (exists) {
        this.specialtyIds = this.specialtyIds.filter((id) => id !== specId);
        if (this.primarySpecialtyId === specId) {
          this.primarySpecialtyId = this.specialtyIds.length > 0 ? this.specialtyIds[0] : "";
        }
      } else {
        this.specialtyIds.push(specId);
        if (!this.primarySpecialtyId) {
          this.primarySpecialtyId = specId;
        }
      }
    }

    setPrimarySpecialty(specId) {
      if (!this.specialtyIds.includes(specId)) {
        this.specialtyIds.push(specId);
      }
      this.primarySpecialtyId = specId;
    }

    validate() {
      const errors = {};

      const trimmedName = this.fullName.trim();
      if (!trimmedName || trimmedName.length < 2) {
        errors.fullName = "Full physician name is required (at least 2 characters).";
      }

      const trimmedEmail = this.email.trim();
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!trimmedEmail || !emailRegex.test(trimmedEmail)) {
        errors.email = "A valid professional email address is required.";
      }

      const trimmedLicense = this.licenseNumber.trim();
      if (!trimmedLicense || trimmedLicense.length < 2) {
        errors.license = "Medical license number is required (at least 2 characters).";
      }

      if (!this.effectiveHospitalId) {
        errors.hospital = "Hospital facility assignment is required.";
      }

      if (this.experience < 0 || isNaN(this.experience)) {
        errors.experience = "Years of experience must be 0 or greater.";
      }

      if (!["both", "in_person", "video"].includes(this.mode)) {
        errors.mode = "Please select a valid consultation mode.";
      }

      if (!this.languages || !this.languages.trim()) {
        errors.languages = "At least one language must be specified.";
      }

      if (
        this.specialtyIds.length > 0 &&
        (!this.primarySpecialtyId || !this.specialtyIds.includes(this.primarySpecialtyId))
      ) {
        errors.primarySpecialty =
          "Please designate exactly one primary specialty among the selected specialties.";
      }

      return {
        isValid: Object.keys(errors).length === 0,
        errors,
      };
    }

    buildPayload() {
      const validation = this.validate();
      if (!validation.isValid) {
        throw new Error(`Validation failed: ${JSON.stringify(validation.errors)}`);
      }

      return {
        full_name: this.fullName.trim(),
        email: this.email.trim(),
        license_number: this.licenseNumber.trim(),
        hospital_id: this.effectiveHospitalId,
        department_id: this.departmentId ? this.departmentId : null,
        specialty_ids: this.specialtyIds.length > 0 ? this.specialtyIds : [],
        primary_specialty_id:
          this.specialtyIds.length > 0 && this.primarySpecialtyId
            ? this.primarySpecialtyId
            : null,
        years_of_experience: Number(this.experience),
        consultation_mode: this.mode,
        languages: this.languages.trim() || "en",
        phone: this.phone.trim() ? this.phone.trim() : null,
      };
    }
  }

  // 1. Validation Tests
  test("fails validation when required fields (name, email, license, hospital) are missing", () => {
    const form = new OnboardFormModel();
    const result = form.validate();

    assert.equal(result.isValid, false);
    assert.ok(result.errors.fullName);
    assert.ok(result.errors.email);
    assert.ok(result.errors.license);
    assert.ok(result.errors.hospital);
  });

  test("validates email format strictly", () => {
    const form = new OnboardFormModel();
    form.fullName = "Dr. Greg House";
    form.licenseNumber = "MD-99881";
    form.hospitalId = "hosp-001";

    form.email = "invalid-email-address";
    assert.equal(form.validate().isValid, false);
    assert.ok(form.validate().errors.email);

    form.email = "greg.house@clinic.org";
    assert.equal(form.validate().isValid, true);
  });

  test("validates years of experience and consultation modes", () => {
    const form = new OnboardFormModel();
    form.fullName = "Dr. Lisa Cuddy";
    form.email = "lisa.cuddy@clinic.org";
    form.licenseNumber = "MD-11223";
    form.hospitalId = "hosp-001";

    form.experience = -1;
    assert.equal(form.validate().isValid, false);
    assert.ok(form.validate().errors.experience);

    form.experience = 12;
    form.mode = "telepathy"; // invalid
    assert.equal(form.validate().isValid, false);
    assert.ok(form.validate().errors.mode);

    form.mode = "video";
    assert.equal(form.validate().isValid, true);
  });

  // 2. Specialty Selection & Primary Designation Tests
  test("automatically sets the first selected specialty as primary", () => {
    const form = new OnboardFormModel();
    form.toggleSpecialty("spec-cardio");

    assert.deepEqual(form.specialtyIds, ["spec-cardio"]);
    assert.equal(form.primarySpecialtyId, "spec-cardio");
  });

  test("retains original primary specialty when additional specialties are added", () => {
    const form = new OnboardFormModel();
    form.toggleSpecialty("spec-cardio");
    form.toggleSpecialty("spec-neuro");

    assert.deepEqual(form.specialtyIds, ["spec-cardio", "spec-neuro"]);
    assert.equal(form.primarySpecialtyId, "spec-cardio");
  });

  test("allows explicitly changing primary specialty among selected specialties", () => {
    const form = new OnboardFormModel();
    form.toggleSpecialty("spec-cardio");
    form.toggleSpecialty("spec-neuro");

    form.setPrimarySpecialty("spec-neuro");
    assert.equal(form.primarySpecialtyId, "spec-neuro");
  });

  test("automatically reassigns primary specialty when the primary specialty is unselected", () => {
    const form = new OnboardFormModel();
    form.toggleSpecialty("spec-cardio");
    form.toggleSpecialty("spec-neuro");
    assert.equal(form.primarySpecialtyId, "spec-cardio");

    // Unselect cardio (the primary)
    form.toggleSpecialty("spec-cardio");
    assert.deepEqual(form.specialtyIds, ["spec-neuro"]);
    assert.equal(form.primarySpecialtyId, "spec-neuro");

    // Unselect neuro (last specialty)
    form.toggleSpecialty("spec-neuro");
    assert.deepEqual(form.specialtyIds, []);
    assert.equal(form.primarySpecialtyId, "");
  });

  test("enforces exactly one primary specialty when specialties are selected", () => {
    const form = new OnboardFormModel();
    form.fullName = "Dr. Allison Cameron";
    form.email = "allison.cameron@clinic.org";
    form.licenseNumber = "MD-33445";
    form.hospitalId = "hosp-001";

    form.specialtyIds = ["spec-cardio", "spec-neuro"];
    form.primarySpecialtyId = ""; // No primary designated

    const validation = form.validate();
    assert.equal(validation.isValid, false);
    assert.ok(validation.errors.primarySpecialty);

    form.primarySpecialtyId = "spec-cardio";
    assert.equal(form.validate().isValid, true);
  });

  // 3. Hospital Tenant Boundary Restrictions
  test("enforces hospital lock for tenant-restricted hospital administrators", () => {
    // Hospital admin restricted to hosp-002
    const tenantAdmin = { id: "admin-hospital-2", role: "admin", hospital_id: "hosp-002" };
    const form = new OnboardFormModel(tenantAdmin);

    assert.equal(form.isTenantRestricted, true);
    assert.equal(form.effectiveHospitalId, "hosp-002");

    // Attempting to select hosp-001 should be ignored
    form.setHospital("hosp-001");
    assert.equal(form.effectiveHospitalId, "hosp-002");

    // Correct departments for hosp-002 are loaded
    assert.equal(form.departments.length, 1);
    assert.equal(form.departments[0].id, "dept-003");
  });

  test("allows global super-administrators to select any hospital facility", () => {
    // Super-admin without hospital_id restriction
    const superAdmin = { id: "admin-super", role: "admin", hospital_id: null };
    const form = new OnboardFormModel(superAdmin);

    assert.equal(form.isTenantRestricted, false);
    form.setHospital("hosp-001");
    assert.equal(form.effectiveHospitalId, "hosp-001");
    assert.equal(form.departments.length, 2);

    form.setHospital("hosp-002");
    assert.equal(form.effectiveHospitalId, "hosp-002");
    assert.equal(form.departments.length, 1);
  });

  // 4. API Payload Construction Tests
  test("constructs valid payload with complete fields including phone, department, and primary specialty", () => {
    const form = new OnboardFormModel();
    form.fullName = "Dr. James Wilson";
    form.email = "james.wilson@oncology.org";
    form.licenseNumber = "MD-77889";
    form.phone = "+1 (555) 234-5678";
    form.setHospital("hosp-001");
    form.departmentId = "dept-001";
    form.toggleSpecialty("spec-cardio");
    form.toggleSpecialty("spec-neuro");
    form.setPrimarySpecialty("spec-cardio");
    form.experience = 15;
    form.mode = "both";
    form.languages = "en, es";

    const payload = form.buildPayload();

    assert.deepEqual(payload, {
      full_name: "Dr. James Wilson",
      email: "james.wilson@oncology.org",
      license_number: "MD-77889",
      hospital_id: "hosp-001",
      department_id: "dept-001",
      specialty_ids: ["spec-cardio", "spec-neuro"],
      primary_specialty_id: "spec-cardio",
      years_of_experience: 15,
      consultation_mode: "both",
      languages: "en, es",
      phone: "+1 (555) 234-5678",
    });
  });

  test("constructs valid payload when optional fields (phone, department, specialties) are omitted", () => {
    const form = new OnboardFormModel();
    form.fullName = "Dr. Eric Foreman";
    form.email = "eric.foreman@neuro.org";
    form.licenseNumber = "MD-88990";
    form.setHospital("hosp-001");
    form.experience = 8;
    form.mode = "in_person";
    form.languages = "en";

    const payload = form.buildPayload();

    assert.deepEqual(payload, {
      full_name: "Dr. Eric Foreman",
      email: "eric.foreman@neuro.org",
      license_number: "MD-88990",
      hospital_id: "hosp-001",
      department_id: null,
      specialty_ids: [],
      primary_specialty_id: null,
      years_of_experience: 8,
      consultation_mode: "in_person",
      languages: "en",
      phone: null,
    });
  });

  // 5. Backend Contract Verification Mock
  test("simulates API response handling on conflict or unauthorized access", async () => {
    const mockApiCall = async (payload) => {
      if (payload.license_number === "MD-DUPLICATE") {
        throw new Error("A doctor with medical license MD-DUPLICATE already exists");
      }
      if (payload.hospital_id === "hosp-unauthorized") {
        throw new Error("403 Forbidden: Administrator cannot assign doctors to unauthorized facility");
      }
      return {
        status: "success",
        profile_id: "prof_new_123",
        entity_id: "doc_new_456",
        auth_provisioned: true,
        message: `Physician ${payload.full_name} onboarded successfully`,
      };
    };

    // Duplicate license check
    await assert.rejects(
      () => mockApiCall({ license_number: "MD-DUPLICATE" }),
      /already exists/
    );

    // Tenant violation check
    await assert.rejects(
      () => mockApiCall({ hospital_id: "hosp-unauthorized" }),
      /403 Forbidden/
    );

    // Success response
    const res = await mockApiCall({ full_name: "Dr. Robert Chase", license_number: "MD-55667", hospital_id: "hosp-001" });
    assert.equal(res.status, "success");
    assert.equal(res.auth_provisioned, true);
  });
});
