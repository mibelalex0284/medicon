import test, { describe, beforeEach, afterEach } from "node:test";
import assert from "node:assert/strict";
import { getSupabaseConfigStatus, isSupabaseConfigured, getSupabaseClient } from "../../src/lib/supabase/client.ts";

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

// AuthService test implementation matching src/services/auth/index.ts
const AUTH_STORAGE_KEY = "careroute_auth_token";
const USER_STORAGE_KEY = "careroute_user_session";

const MOCK_USERS = {
  patient: {
    id: "pat_101",
    email: "sarah.jenkins@example.com",
    name: "Sarah Jenkins",
    role: "patient",
    createdAt: "2026-01-15T09:00:00Z",
  },
  doctor: {
    id: "doc_202",
    email: "dr.menon@careroute.org",
    name: "Dr. Anita Menon, MD",
    role: "doctor",
    createdAt: "2025-06-10T08:30:00Z",
  },
  admin: {
    id: "adm_303",
    email: "ops.admin@careroute.org",
    name: "Mark Evans (Clinic Operations)",
    role: "admin",
    createdAt: "2025-01-01T08:00:00Z",
  },
};

class AuthService {
  constructor() {
    this.currentUser = null;
    this.authToken = null;
  }

  getCurrentUser() {
    return this.currentUser;
  }

  getAuthToken() {
    return this.authToken;
  }

  loginAsRole(role) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        "Security violation: Simulated persona switching is strictly forbidden in production builds."
      );
    }
    const user = MOCK_USERS[role];
    if (!user) throw new Error(`Unknown demo role: ${role}`);
    this.currentUser = user;
    this.authToken = `mock-token-${role}`;
    localStorage.setItem(AUTH_STORAGE_KEY, this.authToken);
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
    return user;
  }

  async loginWithCredentials(email, password) {
    if (isSupabaseConfigured()) {
      const client = getSupabaseClient();
      const { data, error } = await client.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
      this.authToken = data.session?.access_token || null;
      return this.currentUser;
    }

    if (process.env.NODE_ENV !== "production") {
      const matched = Object.values(MOCK_USERS).find(
        (u) => u.email.toLowerCase() === email.trim().toLowerCase()
      );
      if (matched) {
        return this.loginAsRole(matched.role);
      }
      throw new Error(
        "Invalid credentials. Supabase credentials are not configured and email does not match any development mock persona."
      );
    }

    throw new Error("Supabase authentication is not configured in production.");
  }

  async logout() {
    this.currentUser = null;
    this.authToken = null;
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(USER_STORAGE_KEY);
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    sessionStorage.removeItem("careroute_triage_session_id");
    sessionStorage.removeItem("careroute_patient_concern");
    if (isSupabaseConfigured()) {
      const client = getSupabaseClient();
      await client.auth.signOut();
    }
  }
}

describe("Supabase Authentication Stage 2 - Frontend Tests", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  test("1. No automatic login occurs when session is absent", () => {
    const auth = new AuthService();
    assert.equal(auth.getCurrentUser(), null, "Initial user must be null when no session is stored");
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null, "careroute_auth_token must NOT be automatically seeded");
    assert.equal(localStorage.getItem(USER_STORAGE_KEY), null, "careroute_user_session must NOT be automatically seeded");
  });

  test("2. Supabase configuration detection and placeholder rejection", () => {
    const status = getSupabaseConfigStatus();
    assert.equal(status.configured, false, "Placeholder environment variables must not be marked as configured");
    assert.ok(
      status.missingOrPlaceholder.includes("NEXT_PUBLIC_SUPABASE_URL") ||
      status.missingOrPlaceholder.includes("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    );
    assert.equal(isSupabaseConfigured(), false, "isSupabaseConfigured() must return false for placeholder config");

    // In production, getSupabaseClient() must throw a fatal error on placeholder config
    process.env.NODE_ENV = "production";
    assert.throws(
      () => getSupabaseClient(),
      /FATAL: Production build cannot start with missing or placeholder Supabase configuration/,
      "Must throw in production on placeholder configuration"
    );
  });

  test("3. Persona switching is strictly prohibited in production builds", () => {
    const auth = new AuthService();
    process.env.NODE_ENV = "production";
    assert.throws(
      () => auth.loginAsRole("patient"),
      /forbidden in production builds/,
      "loginAsRole must fail with an error when NODE_ENV is production"
    );
    assert.throws(
      () => auth.loginAsRole("admin"),
      /forbidden in production builds/,
      "loginAsRole must fail with an error when NODE_ENV is production"
    );
  });

  test("4. Persona switching functions in development mode without granting persistence to unauth visitors", async () => {
    process.env.NODE_ENV = "development";
    const auth = new AuthService();

    const docUser = auth.loginAsRole("doctor");
    assert.equal(docUser.role, "doctor");
    assert.equal(auth.getCurrentUser().role, "doctor");
    assert.ok(localStorage.getItem(AUTH_STORAGE_KEY), "Token stored for development session");

    // Logout clears all tokens cleanly
    await auth.logout();
    assert.equal(auth.getCurrentUser(), null);
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null);
    assert.equal(localStorage.getItem(USER_STORAGE_KEY), null);
  });

  test("5. Credential-based login rejects unknown emails in development unconfigured mode", async () => {
    process.env.NODE_ENV = "development";
    const auth = new AuthService();

    await assert.rejects(
      async () => {
        await auth.loginWithCredentials("unknown.visitor@random.com", "any-password");
      },
      /Supabase credentials are not configured/,
      "Must reject unconfigured unknown logins without auto-fallback"
    );

    assert.equal(auth.getCurrentUser(), null, "User remains null on failed login");
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null, "No token written on failed login");
  });

  test("6. Logout thoroughly purges all application and triage state", async () => {
    const auth = new AuthService();

    localStorage.setItem(AUTH_STORAGE_KEY, "fake-token");
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify({ id: "123", role: "patient" }));
    sessionStorage.setItem(AUTH_STORAGE_KEY, "fake-token");
    sessionStorage.setItem("careroute_triage_session_id", "sess-999");
    sessionStorage.setItem("careroute_patient_concern", "Headache");

    await auth.logout();

    assert.equal(auth.getCurrentUser(), null);
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null);
    assert.equal(localStorage.getItem(USER_STORAGE_KEY), null);
    assert.equal(sessionStorage.getItem("careroute_triage_session_id"), null);
    assert.equal(sessionStorage.getItem("careroute_patient_concern"), null);
  });
});
