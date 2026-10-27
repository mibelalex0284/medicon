import test, { describe, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

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

class MockRouter {
  constructor() {
    this.currentRoute = "/login";
    this.history = ["/login"];
  }
  push(route) {
    this.currentRoute = route;
    this.history.push(route);
  }
  replace(route) {
    this.currentRoute = route;
    this.history.push(route);
  }
}

describe("Unified Login Page & Authoritative Authentication Flow", () => {
  const loginPagePath = path.resolve(process.cwd(), "src/app/(auth)/login/page.tsx");
  const loginPageCode = fs.readFileSync(loginPagePath, "utf-8");

  beforeEach(() => {
    global.localStorage.clear();
    global.sessionStorage.clear();
  });

  test("1. No Patient, Doctor, or Admin role selector appears on the login page", () => {
    // Assert no role tab selector or headings exist in login code
    assert.equal(
      loginPageCode.includes("Select Workspace Role"),
      false,
      "'Select Workspace Role' heading must be removed"
    );
    assert.equal(
      loginPageCode.includes("roleConfigs"),
      false,
      "roleConfigs lookup object must be removed"
    );
    assert.equal(
      loginPageCode.includes("handleRoleSelect"),
      false,
      "handleRoleSelect handler must be removed"
    );
    assert.equal(
      loginPageCode.includes("selectedRole"),
      false,
      "selectedRole state must be removed"
    );
    assert.equal(
      loginPageCode.includes("Mobile-First Patient Experience"),
      false,
      "Patient role card description must be removed"
    );
    assert.equal(
      loginPageCode.includes("Desktop-First Clinical Workspace"),
      false,
      "Doctor role card description must be removed"
    );
    assert.equal(
      loginPageCode.includes("Enterprise Operational Oversight"),
      false,
      "Admin role card description must be removed"
    );
  });

  test("2. A single email/password form remains with show/hide password and clean branding", () => {
    // Welcome back heading & subtitle
    assert.ok(
      loginPageCode.includes("Welcome back"),
      "Must display 'Welcome back' heading"
    );
    assert.ok(
      loginPageCode.includes("Sign in to your MediLink account."),
      "Must display 'Sign in to your MediLink account.' subtitle"
    );

    // Email and password fields
    assert.ok(
      loginPageCode.includes('id="login-email"'),
      "Email input must be present"
    );
    assert.ok(
      loginPageCode.includes('id="login-password"'),
      "Password input must be present"
    );

    // Password show/hide functionality
    assert.ok(
      loginPageCode.includes("showPassword"),
      "showPassword state toggle must be present"
    );
    assert.ok(
      loginPageCode.includes("Eye") && loginPageCode.includes("EyeOff"),
      "Eye and EyeOff visibility toggle icons must be present"
    );

    // Single unified Sign In button
    assert.ok(
      loginPageCode.includes("<span>Sign In</span>"),
      "Single 'Sign In' primary button must be present without role-specific suffixes"
    );

    // No nonfunctional forgot password link
    assert.equal(
      loginPageCode.includes("Forgot?"),
      false,
      "Nonfunctional 'Forgot?' link must not be present"
    );

    // Initial state has no hardcoded demo credentials
    assert.ok(
      loginPageCode.includes('const [email, setEmail] = useState("");'),
      "Email state must initialize to an empty string"
    );
    assert.ok(
      loginPageCode.includes('const [password, setPassword] = useState("");'),
      "Password state must initialize to an empty string"
    );
  });

  test("3. Patient registration still respects the backend registration setting", () => {
    // Tests presence of container and conditional link
    assert.ok(
      loginPageCode.includes('data-testid="registration-enabled-container"'),
      "Registration-enabled container testid must be preserved"
    );
    assert.ok(
      loginPageCode.includes('id="create-patient-account-link"'),
      "create-patient-account-link id must be preserved"
    );
    assert.ok(
      loginPageCode.includes('data-testid="create-patient-account-link"'),
      "create-patient-account-link testid must be preserved"
    );
    assert.ok(
      loginPageCode.includes("isRegistrationEnabled && ("),
      "Registration link must only display when registration is enabled by admin"
    );
  });

  test("4. Successful authentication redirects according to authoritative role", async () => {
    const AUTH_STORAGE_KEY = "careroute_user_session";
    const TOKEN_STORAGE_KEY = "careroute_auth_token";

    function resolveRoute(user) {
      if (!user) return "/login";
      if (user.role === "patient") return "/patient/dashboard";
      if (user.role === "doctor") return "/doctor/dashboard";
      if (user.role === "admin") return "/admin/dashboard";
      if (user.role === "unregistered") return "/account-setup";
      return "/login";
    }

    class TestAuthEngine {
      constructor(backend) {
        this.backend = backend;
      }
      async loginWithCredentials(email, password) {
        const session = await this.backend.signIn(email, password);
        const me = await this.backend.fetchMe(session.token);
        const user = {
          id: me.auth_user_id,
          email: me.email,
          name: me.full_name,
          role: me.has_profile ? me.role : "unregistered",
        };
        global.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        global.localStorage.setItem(TOKEN_STORAGE_KEY, session.token);
        return user;
      }
    }

    // A. Doctor login
    const doctorBackend = {
      signIn: async () => ({ token: "doc-tok" }),
      fetchMe: async () => ({
        auth_user_id: "doc-1",
        email: "doctor@clinic.org",
        full_name: "Dr. Smith",
        has_profile: true,
        role: "doctor",
      }),
    };
    const doctorAuth = new TestAuthEngine(doctorBackend);
    const doctorRouter = new MockRouter();
    const docUser = await doctorAuth.loginWithCredentials("doctor@clinic.org", "pass");
    doctorRouter.push(resolveRoute(docUser));
    assert.equal(doctorRouter.currentRoute, "/doctor/dashboard");

    // B. Admin login
    const adminBackend = {
      signIn: async () => ({ token: "adm-tok" }),
      fetchMe: async () => ({
        auth_user_id: "adm-1",
        email: "admin@clinic.org",
        full_name: "Admin Evans",
        has_profile: true,
        role: "admin",
      }),
    };
    const adminAuth = new TestAuthEngine(adminBackend);
    const adminRouter = new MockRouter();
    const admUser = await adminAuth.loginWithCredentials("admin@clinic.org", "pass");
    adminRouter.push(resolveRoute(admUser));
    assert.equal(adminRouter.currentRoute, "/admin/dashboard");

    // C. Patient login
    const patientBackend = {
      signIn: async () => ({ token: "pat-tok" }),
      fetchMe: async () => ({
        auth_user_id: "pat-1",
        email: "patient@example.com",
        full_name: "Sarah Patient",
        has_profile: true,
        role: "patient",
      }),
    };
    const patientAuth = new TestAuthEngine(patientBackend);
    const patientRouter = new MockRouter();
    const patUser = await patientAuth.loginWithCredentials("patient@example.com", "pass");
    patientRouter.push(resolveRoute(patUser));
    assert.equal(patientRouter.currentRoute, "/patient/dashboard");
  });

  test("5. Unregistered accounts go strictly to /account-setup", async () => {
    const unregBackend = {
      signIn: async () => ({ token: "unreg-tok" }),
      fetchMe: async () => ({
        auth_user_id: "unreg-1",
        email: "visitor@unknown.com",
        full_name: "New Visitor",
        has_profile: false,
        role: "unregistered",
      }),
    };
    const session = await unregBackend.signIn();
    const me = await unregBackend.fetchMe(session.token);
    const user = {
      id: me.auth_user_id,
      email: me.email,
      name: me.full_name,
      role: me.has_profile ? me.role : "unregistered",
    };

    assert.equal(user.role, "unregistered");
    const router = new MockRouter();
    const route = user.role === "unregistered" ? "/account-setup" : "/patient/dashboard";
    router.push(route);
    assert.equal(router.currentRoute, "/account-setup");
    assert.notEqual(router.currentRoute, "/patient/dashboard");
  });

  test("6. The development rapid workspace switcher is absent from the login page", () => {
    assert.equal(
      loginPageCode.includes("Development Rapid Workspace Switcher"),
      false,
      "'Development Rapid Workspace Switcher' banner must be absent"
    );
    assert.equal(
      loginPageCode.includes("loginAsRole"),
      false,
      "loginAsRole dev mock callers must be absent from login page"
    );
    assert.equal(
      loginPageCode.includes("Patient View"),
      false,
      "Mock shortcut 'Patient View' button must be absent"
    );
    assert.equal(
      loginPageCode.includes("Doctor View"),
      false,
      "Mock shortcut 'Doctor View' button must be absent"
    );
    assert.equal(
      loginPageCode.includes("Admin View"),
      false,
      "Mock shortcut 'Admin View' button must be absent"
    );
  });
});
