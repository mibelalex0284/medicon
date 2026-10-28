import test, { describe, beforeEach } from "node:test";
import assert from "node:assert/strict";

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

// Model reproducing AuthService getAuthToken and adminOnboardDoctor behavior
class AuthTestService {
  constructor(mockSupabaseClient = null) {
    this.mockSupabaseClient = mockSupabaseClient;
  }

  async getAuthToken(explicitToken = null) {
    if (explicitToken) return explicitToken;

    // 1. Authoritative Supabase session: query live client for current access token
    if (this.mockSupabaseClient) {
      try {
        const { data } = await this.mockSupabaseClient.auth.getSession();
        if (data?.session?.access_token) {
          global.localStorage.setItem("careroute_auth_token", data.session.access_token);
          return data.session.access_token;
        }
      } catch {
        // Fallback to storage
      }
    }

    // 2. Storage fallback
    return (
      global.localStorage.getItem("careroute_auth_token") ||
      global.sessionStorage.getItem("careroute_auth_token") ||
      null
    );
  }

  async adminOnboardDoctor(payload, adminToken = null) {
    const token = await this.getAuthToken(adminToken);
    if (!token) {
      throw new Error("Authentication token missing. Please sign in again.");
    }

    const res = await global.fetch("http://localhost:8000/api/v1/admin/doctors/onboard", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const message =
        err.error?.message ||
        err.detail ||
        err.message ||
        `Failed to onboard physician (HTTP ${res.status})`;
      const errorObj = new Error(message);
      if (err.error?.code || err.code) {
        errorObj.code = err.error?.code || err.code;
      }
      throw errorObj;
    }

    return res.json();
  }
}

describe("Physician Onboarding Authentication Flow & Safe Error Extraction", () => {
  beforeEach(() => {
    global.localStorage.clear();
    global.sessionStorage.clear();
  });

  test("1. Rejects onboarding immediately with clear message if authentication token is missing", async () => {
    const authService = new AuthTestService(null);

    // Ensure no token in storage
    assert.equal(global.localStorage.getItem("careroute_auth_token"), null);

    await assert.rejects(
      async () => {
        await authService.adminOnboardDoctor({
          full_name: "Dr. Test Missing Token",
          email: "missing.token@hospital.org",
          license_number: "LIC-MISSING",
          hospital_id: "hosp-001",
        });
      },
      /Authentication token missing. Please sign in again./
    );
  });

  test("2. Extracts and displays safe backend error message from envelope instead of generic fallback", async () => {
    const authService = new AuthTestService(null);
    global.localStorage.setItem("careroute_auth_token", "mock-admin-token");

    const originalFetch = global.fetch;
    try {
      global.fetch = async (url, options) => {
        // Assert Authorization header is sent with Bearer
        assert.equal(options.headers["Authorization"], "Bearer mock-admin-token");
        return {
          ok: false,
          status: 409,
          json: async () => ({
            error: {
              code: "LICENSE_ALREADY_REGISTERED",
              message: "Physician license number 'LIC-DUPLICATE-999' is already registered.",
            },
          }),
        };
      };

      await assert.rejects(
        async () => {
          await authService.adminOnboardDoctor({
            full_name: "Dr. Duplicate",
            email: "duplicate@hospital.org",
            license_number: "LIC-DUPLICATE-999",
            hospital_id: "hosp-001",
          });
        },
        /Physician license number 'LIC-DUPLICATE-999' is already registered./
      );
    } finally {
      global.fetch = originalFetch;
    }
  });

  test("3. Sends explicit or live refreshed Supabase access token in Authorization header", async () => {
    const mockSupabase = {
      auth: {
        getSession: async () => ({
          data: {
            session: {
              access_token: "live-supabase-jwt-token-es256",
            },
          },
        }),
      },
    };
    const authService = new AuthTestService(mockSupabase);

    let capturedHeaders = null;
    const originalFetch = global.fetch;
    try {
      global.fetch = async (url, options) => {
        capturedHeaders = options.headers;
        return {
          ok: true,
          status: 201,
          json: async () => ({
            status: "created",
            profile_id: "prof-123",
            auth_user_id: "auth-123",
            role: "doctor",
            full_name: "Dr. Valid",
            email: "valid@hospital.org",
            entity_id: "doc-123",
            auth_provisioned: true,
            message: "Physician onboarded successfully.",
          }),
        };
      };

      const result = await authService.adminOnboardDoctor({
        full_name: "Dr. Valid",
        email: "valid@hospital.org",
        license_number: "LIC-VALID-123",
        hospital_id: "hosp-001",
      });

      assert.ok(capturedHeaders);
      assert.equal(capturedHeaders["Authorization"], "Bearer live-supabase-jwt-token-es256");
      assert.equal(result.status, "created");
      // Check synced to storage
      assert.equal(global.localStorage.getItem("careroute_auth_token"), "live-supabase-jwt-token-es256");
    } finally {
      global.fetch = originalFetch;
    }
  });

  test("4. Surfaces 401 Unauthorized backend error code and details cleanly", async () => {
    const authService = new AuthTestService(null);
    global.localStorage.setItem("careroute_auth_token", "expired-jwt-token");

    const originalFetch = global.fetch;
    try {
      global.fetch = async (url, options) => {
        return {
          ok: false,
          status: 401,
          json: async () => ({
            error: {
              code: "TOKEN_EXPIRED",
              message: "Authentication token has expired",
            },
          }),
        };
      };

      await assert.rejects(
        async () => {
          await authService.adminOnboardDoctor({
            full_name: "Dr. Expired",
            email: "expired@hospital.org",
            license_number: "LIC-EXPIRED",
            hospital_id: "hosp-001",
          });
        },
        (err) => {
          assert.equal(err.message, "Authentication token has expired");
          assert.equal(err.code, "TOKEN_EXPIRED");
          return true;
        }
      );
    } finally {
      global.fetch = originalFetch;
    }
  });
});
