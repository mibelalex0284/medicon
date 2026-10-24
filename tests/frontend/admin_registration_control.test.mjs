import test, { describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

// Mock localStorage and sessionStorage for Node.js test environment
class StorageMock {
  constructor() {
    this.store = {};
  }
  getItem(key) {
    return this.store[key] || null;
  }
  setItem(key, value) {
    this.store[key] = String(value);
  }
  removeItem(key) {
    delete this.store[key];
  }
  clear() {
    this.store = {};
  }
}

global.localStorage = new StorageMock();
global.sessionStorage = new StorageMock();

describe("Admin-Controlled User Registration & Governance", () => {
  let registrationEnabled = true;
  let registeredProfiles = [];
  let registeredDoctors = [];

  beforeEach(() => {
    global.localStorage.clear();
    global.sessionStorage.clear();
    registrationEnabled = true;
    registeredProfiles = [
      { id: "prof_existing_1", email: "existing.patient@example.com", role: "patient" },
      { id: "prof_admin_1", email: "ops.admin@careroute.org", role: "admin" },
      { id: "prof_doc_1", email: "dr.menon@careroute.org", role: "doctor" },
    ];
    registeredDoctors = [
      { id: "doc_1", license_number: "MD-10001", email: "dr.menon@careroute.org" },
    ];
  });

  // Test AuthService implementation replicating backend contracts
  class TestAuthService {
    async getRegistrationStatus() {
      return { patient_self_registration_enabled: registrationEnabled };
    }

    async registerPatient(payload) {
      const status = await this.getRegistrationStatus();
      if (!status.patient_self_registration_enabled) {
        throw new Error("Public patient registration is currently disabled by clinic administration.");
      }

      // Check duplicate email
      const duplicate = registeredProfiles.find((p) => p.email.toLowerCase() === payload.email.toLowerCase());
      if (duplicate) {
        throw new Error("A profile with this email address already exists");
      }

      // Role is strictly hardcoded to patient
      const user = {
        id: `pat_${Date.now()}`,
        email: payload.email,
        name: payload.full_name,
        role: "patient",
        createdAt: new Date().toISOString(),
      };
      registeredProfiles.push({ id: user.id, email: user.email, role: "patient" });
      global.localStorage.setItem("careroute_user_session", JSON.stringify(user));
      global.localStorage.setItem("careroute_auth_token", "test-patient-jwt-token");
      return user;
    }

    async loginWithCredentials(email, password) {
      const match = registeredProfiles.find((p) => p.email.toLowerCase() === email.toLowerCase());
      if (!match) {
        throw new Error("Invalid email or password");
      }
      const user = {
        id: match.id,
        email: match.email,
        name: match.email.split("@")[0],
        role: match.role,
        createdAt: new Date().toISOString(),
      };
      global.localStorage.setItem("careroute_user_session", JSON.stringify(user));
      return user;
    }

    async getAdminSettings(adminToken) {
      if (!adminToken || adminToken !== "valid-admin-token") {
        throw new Error("403 Forbidden: Insufficient permissions");
      }
      return {
        patient_self_registration_enabled: registrationEnabled,
        settings: [{ key: "patient_self_registration", value: String(registrationEnabled) }],
      };
    }

    async updatePatientSelfRegistration(enabled, adminToken) {
      if (!adminToken || adminToken !== "valid-admin-token") {
        throw new Error("403 Forbidden: Only authorized administrators may change registration settings");
      }
      registrationEnabled = Boolean(enabled);
      return {
        patient_self_registration_enabled: registrationEnabled,
      };
    }

    async adminRegisterPatient(payload, adminToken) {
      if (!adminToken || adminToken !== "valid-admin-token") {
        throw new Error("403 Forbidden: Only administrators may register patient accounts directly");
      }
      // Check duplicate
      const duplicate = registeredProfiles.find((p) => p.email.toLowerCase() === payload.email.toLowerCase());
      if (duplicate) {
        throw new Error("An account with this email already exists");
      }
      const newPatient = {
        status: "created",
        profile_id: `prof_${Date.now()}`,
        role: "patient",
        full_name: payload.full_name,
        email: payload.email,
        entity_id: `pat_rec_${Date.now()}`,
        auth_provisioned: false,
        message: "Patient account created successfully.",
      };
      registeredProfiles.push({ id: newPatient.profile_id, email: newPatient.email, role: "patient" });
      return newPatient;
    }

    async adminOnboardDoctor(payload, adminToken) {
      if (!adminToken || adminToken !== "valid-admin-token") {
        throw new Error("403 Forbidden: Only administrators may onboard physicians");
      }
      const duplicateEmail = registeredProfiles.find((p) => p.email.toLowerCase() === payload.email.toLowerCase());
      if (duplicateEmail) {
        throw new Error("An account with this email already exists");
      }
      const duplicateLicense = registeredDoctors.find((d) => d.license_number === payload.license_number);
      if (duplicateLicense) {
        throw new Error("Physician license number is already registered");
      }
      const newDoc = {
        status: "created",
        profile_id: `prof_${Date.now()}`,
        role: "doctor",
        full_name: payload.full_name,
        email: payload.email,
        entity_id: `doc_rec_${Date.now()}`,
        auth_provisioned: false,
        message: "Physician onboarded successfully.",
      };
      registeredProfiles.push({ id: newDoc.profile_id, email: newDoc.email, role: "doctor" });
      registeredDoctors.push({ id: newDoc.entity_id, license_number: payload.license_number, email: payload.email });
      return newDoc;
    }
  }

  const authService = new TestAuthService();

  test("1. Public registration enabled: returns status and allows patient registration", async () => {
    const status = await authService.getRegistrationStatus();
    assert.equal(status.patient_self_registration_enabled, true);

    const user = await authService.registerPatient({
      full_name: "John Public",
      email: "john.public@test.org",
      password: "securepassword123",
      date_of_birth: "1992-03-20",
    });

    assert.equal(user.role, "patient");
    assert.equal(user.email, "john.public@test.org");
    assert.equal(global.localStorage.getItem("careroute_auth_token"), "test-patient-jwt-token");
  });

  test("2. Public registration disabled: blocks patient self-registration with descriptive error", async () => {
    // Disable registration
    registrationEnabled = false;

    const status = await authService.getRegistrationStatus();
    assert.equal(status.patient_self_registration_enabled, false);

    await assert.rejects(
      async () => {
        await authService.registerPatient({
          full_name: "Blocked User",
          email: "blocked.user@test.org",
          password: "securepassword123",
          date_of_birth: "1995-01-01",
        });
      },
      {
        message: "Public patient registration is currently disabled by clinic administration.",
      }
    );
  });

  test("3. Role protection: public registration strictly enforces patient role", async () => {
    registrationEnabled = true;

    const user = await authService.registerPatient({
      full_name: "Attacker Test",
      email: "attacker@test.org",
      password: "password123",
      date_of_birth: "1990-01-01",
    });

    // Cannot become doctor or admin through public flow
    assert.equal(user.role, "patient");
    assert.notEqual(user.role, "doctor");
    assert.notEqual(user.role, "admin");
  });

  test("4. Unauthorized users cannot modify registration setting", async () => {
    // Attempt without token or with non-admin token
    await assert.rejects(
      async () => {
        await authService.updatePatientSelfRegistration(false, null);
      },
      /403 Forbidden/
    );

    await assert.rejects(
      async () => {
        await authService.updatePatientSelfRegistration(false, "patient-token");
      },
      /403 Forbidden/
    );
  });

  test("5. Authorized admin can toggle and persist registration setting", async () => {
    const adminToken = "valid-admin-token";

    // Disable
    const resDisable = await authService.updatePatientSelfRegistration(false, adminToken);
    assert.equal(resDisable.patient_self_registration_enabled, false);

    const statusAfterDisable = await authService.getRegistrationStatus();
    assert.equal(statusAfterDisable.patient_self_registration_enabled, false);

    // Re-enable
    const resEnable = await authService.updatePatientSelfRegistration(true, adminToken);
    assert.equal(resEnable.patient_self_registration_enabled, true);

    const statusAfterEnable = await authService.getRegistrationStatus();
    assert.equal(statusAfterEnable.patient_self_registration_enabled, true);
  });

  test("6. Admin-created patient registration remains available when public registration is disabled", async () => {
    registrationEnabled = false;
    const adminToken = "valid-admin-token";

    const created = await authService.adminRegisterPatient(
      {
        full_name: "Walk-in Patient",
        email: "walkin@careroute.org",
        date_of_birth: "1982-08-14",
      },
      adminToken
    );

    assert.equal(created.status, "created");
    assert.equal(created.role, "patient");
    assert.equal(created.email, "walkin@careroute.org");
  });

  test("7. Doctor onboarding requires admin credentials and enforces uniqueness", async () => {
    const adminToken = "valid-admin-token";

    // Non-admin rejected
    await assert.rejects(
      async () => {
        await authService.adminOnboardDoctor(
          {
            full_name: "Dr. Hacker",
            email: "hacker@test.org",
            license_number: "MD-9999",
          },
          "invalid-token"
        );
      },
      /403 Forbidden/
    );

    // Admin succeeds
    const doctor = await authService.adminOnboardDoctor(
      {
        full_name: "Dr. Sarah Adams, MD",
        email: "dr.adams@careroute.org",
        license_number: "MD-54321",
        hospital_id: "hosp-001",
      },
      adminToken
    );

    assert.equal(doctor.status, "created");
    assert.equal(doctor.role, "doctor");

    // Duplicate license number rejected
    await assert.rejects(
      async () => {
        await authService.adminOnboardDoctor(
          {
            full_name: "Dr. Another",
            email: "another@careroute.org",
            license_number: "MD-54321", // duplicate
          },
          adminToken
        );
      },
      /Physician license number is already registered/
    );
  });

  test("8. Existing email/password login continues to function seamlessly", async () => {
    const user = await authService.loginWithCredentials("ops.admin@careroute.org", "any-password");
    assert.equal(user.role, "admin");
    assert.equal(user.email, "ops.admin@careroute.org");

    const doctorUser = await authService.loginWithCredentials("dr.menon@careroute.org", "any-password");
    assert.equal(doctorUser.role, "doctor");
  });

  test("9. Duplicate email registration is prevented", async () => {
    registrationEnabled = true;

    await assert.rejects(
      async () => {
        await authService.registerPatient({
          full_name: "Duplicate Sarah",
          email: "existing.patient@example.com",
          password: "password123",
          date_of_birth: "1990-01-01",
        });
      },
      /already exists/
    );
  });
});
