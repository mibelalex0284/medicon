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

describe("CareRoute-X Auth Failure Remediation & Race Prevention", () => {
  const AUTH_STORAGE_KEY = "careroute_user_session";
  const TOKEN_STORAGE_KEY = "careroute_auth_token";

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  // Test implementation of AuthService mirroring src/services/auth/index.ts
  class AuthServiceTest {
    constructor(mockFetch, mockSupabase) {
      this.mockFetch = mockFetch;
      this.mockSupabase = mockSupabase;
      this.currentUser = null;
      this.isLoggingIn = false;
      this.logoutCallCount = 0;
      this.inFlightProfileFetches = new Map();
    }

    getIsLoggingIn() {
      return this.isLoggingIn;
    }

    getCurrentUser() {
      const stored = localStorage.getItem(AUTH_STORAGE_KEY);
      if (stored) {
        try {
          return JSON.parse(stored);
        } catch {
          return this.currentUser;
        }
      }
      return this.currentUser;
    }

    async fetchAuthoritativeProfile(token) {
      const existing = this.inFlightProfileFetches.get(token);
      if (existing) {
        return existing;
      }

      const fetchPromise = this._executeFetchAuthoritativeProfile(token);
      this.inFlightProfileFetches.set(token, fetchPromise);
      try {
        return await fetchPromise;
      } finally {
        this.inFlightProfileFetches.delete(token);
      }
    }

    async _executeFetchAuthoritativeProfile(token) {
      const res = await this.mockFetch("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (res.status === 401) {
        let errorCode = "UNAUTHORIZED";
        let errorMessage = "Authentication failed. Please verify your credentials and sign in again.";
        try {
          const errorJson = await res.json();
          errorCode = errorJson.error?.code || errorJson.code || errorCode;
          errorMessage = errorJson.error?.message || errorJson.message || errorMessage;
        } catch {
          // Body not JSON
        }

        if (errorCode === "TOKEN_EXPIRED") {
          const expiredErr = new Error("AUTHENTICATION_EXPIRED");
          expiredErr.code = "TOKEN_EXPIRED";
          throw expiredErr;
        }

        const authErr = new Error(errorMessage);
        authErr.code = errorCode;
        throw authErr;
      }

      if (!res.ok) {
        let detailMsg = `status ${res.status}`;
        try {
          const errorJson = await res.json();
          detailMsg = errorJson.error?.message || errorJson.message || errorJson.detail || detailMsg;
        } catch {
          // Body not JSON
        }
        throw new Error(
          `Server error: Failed to verify account role with backend (${detailMsg}).`
        );
      }

      const me = await res.json();
      if (
        me.has_profile &&
        me.role &&
        ["patient", "doctor", "admin"].includes(String(me.role).toLowerCase())
      ) {
        return {
          role: String(me.role).toLowerCase(),
          hasProfile: true,
          fullName: me.full_name,
          email: me.email,
          profileId: me.profile_id,
          hospitalId: me.hospital_id || null,
        };
      }

      return {
        role: "unregistered",
        hasProfile: false,
        fullName: me.full_name,
        email: me.email,
        profileId: undefined,
        hospitalId: me.hospital_id || null,
      };
    }

    async logout() {
      this.logoutCallCount++;
      if (this.mockSupabase) {
        await this.mockSupabase.auth.signOut();
      }
      this.currentUser = null;
      localStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }

    async restoreSession() {
      if (this.isLoggingIn) {
        return this.currentUser;
      }

      if (this.mockSupabase) {
        const { data, error } = await this.mockSupabase.auth.getSession();
        if (error || !data.session) {
          await this.logout();
          return null;
        }

        const token = data.session.access_token;
        localStorage.setItem(TOKEN_STORAGE_KEY, token);

        let authResult;
        try {
          authResult = await this.fetchAuthoritativeProfile(token);
        } catch (err) {
          if (err.message === "AUTHENTICATION_EXPIRED") {
            await this.logout();
            return null;
          }
          this.currentUser = null;
          localStorage.removeItem(AUTH_STORAGE_KEY);
          throw err;
        }

        const user = {
          id: data.session.user.id,
          email: data.session.user.email || "",
          name: authResult.fullName || data.session.user.email || "User",
          role: authResult.role,
          hospital_id: authResult.hospitalId || null,
        };
        this.currentUser = user;
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        return user;
      }

      return this.getCurrentUser();
    }

    async loginWithCredentials(email, password) {
      this.isLoggingIn = true;
      try {
        if (!this.mockSupabase) {
          throw new Error("Supabase is not configured");
        }

        const { data, error } = await this.mockSupabase.auth.signInWithPassword({
          email,
          password,
        });

        if (error || !data.session) {
          throw new Error(error?.message || "Invalid email or password");
        }

        const token = data.session.access_token;
        localStorage.setItem(TOKEN_STORAGE_KEY, token);

        let authResult;
        try {
          authResult = await this.fetchAuthoritativeProfile(token);
        } catch (err) {
          this.currentUser = null;
          localStorage.removeItem(AUTH_STORAGE_KEY);
          throw new Error(
            err.message || "Failed to resolve authenticated role permissions. Please try again."
          );
        }

        const user = {
          id: data.session.user.id,
          email: data.session.user.email || email,
          name: authResult.fullName || email,
          role: authResult.role,
          hospital_id: authResult.hospitalId || null,
        };

        this.currentUser = user;
        localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
        return user;
      } finally {
        this.isLoggingIn = false;
      }
    }
  }

  test("1. Patient login resolves authoritative role from backend profile", async () => {
    const mockFetch = async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        has_profile: true,
        role: "patient",
        full_name: "Sarah Jenkins",
        email: "patient@example.com",
        profile_id: "prof_pat_1",
      }),
    });

    const mockSupabase = {
      auth: {
        signInWithPassword: async () => ({
          data: {
            session: { access_token: "patient-token", user: { id: "u_pat_1", email: "patient@example.com" } },
          },
          error: null,
        }),
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);
    const user = await auth.loginWithCredentials("patient@example.com", "Password123!");

    assert.equal(user.role, "patient");
    assert.equal(user.name, "Sarah Jenkins");
    assert.equal(auth.getCurrentUser()?.role, "patient");
  });

  test("2. Doctor login resolves authoritative role from backend profile", async () => {
    const mockFetch = async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        has_profile: true,
        role: "doctor",
        full_name: "Dr. Anita Menon, MD",
        email: "doctor@example.com",
        profile_id: "prof_doc_1",
        hospital_id: "hosp_alpha",
      }),
    });

    const mockSupabase = {
      auth: {
        signInWithPassword: async () => ({
          data: {
            session: { access_token: "doc-token", user: { id: "u_doc_1", email: "doctor@example.com" } },
          },
          error: null,
        }),
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);
    const user = await auth.loginWithCredentials("doctor@example.com", "DocPassword123!");

    assert.equal(user.role, "doctor");
    assert.equal(user.hospital_id, "hosp_alpha");
  });

  test("3. Admin login resolves authoritative role from backend profile", async () => {
    const mockFetch = async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        has_profile: true,
        role: "admin",
        full_name: "Ops Admin",
        email: "admin@example.com",
        profile_id: "prof_adm_1",
      }),
    });

    const mockSupabase = {
      auth: {
        signInWithPassword: async () => ({
          data: {
            session: { access_token: "admin-token", user: { id: "u_adm_1", email: "admin@example.com" } },
          },
          error: null,
        }),
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);
    const user = await auth.loginWithCredentials("admin@example.com", "AdminPass123!");

    assert.equal(user.role, "admin");
  });

  test("4. Expired JWT: throws AUTHENTICATION_EXPIRED when code is TOKEN_EXPIRED", async () => {
    const mockFetch = async () => ({
      status: 401,
      ok: false,
      json: async () => ({
        error: { code: "TOKEN_EXPIRED", message: "Authentication token has expired" },
      }),
    });

    const auth = new AuthServiceTest(mockFetch, null);
    await assert.rejects(
      async () => await auth.fetchAuthoritativeProfile("expired-token"),
      (err) => {
        assert.equal(err.message, "AUTHENTICATION_EXPIRED");
        assert.equal(err.code, "TOKEN_EXPIRED");
        return true;
      }
    );
  });

  test("5. Clock skew and other 401s preserve actual backend error message and code", async () => {
    const mockFetch = async () => ({
      status: 401,
      ok: false,
      json: async () => ({
        error: {
          code: "TOKEN_NOT_YET_VALID",
          message: "Authentication token is not yet valid: The token is not yet valid (iat)",
        },
      }),
    });

    const auth = new AuthServiceTest(mockFetch, null);
    await assert.rejects(
      async () => await auth.fetchAuthoritativeProfile("future-token"),
      (err) => {
        // Must NOT report AUTHENTICATION_EXPIRED
        assert.notEqual(err.message, "AUTHENTICATION_EXPIRED");
        assert.equal(err.code, "TOKEN_NOT_YET_VALID");
        assert.match(err.message, /not yet valid/);
        return true;
      }
    );
  });

  test("6. In-flight profile requests for the same token are deduplicated", async () => {
    let callCount = 0;
    const mockFetch = async () => {
      callCount++;
      return {
        status: 200,
        ok: true,
        json: async () => ({
          has_profile: true,
          role: "patient",
          full_name: "Sarah Jenkins",
        }),
      };
    };

    const auth = new AuthServiceTest(mockFetch, null);
    const [p1, p2] = await Promise.all([
      auth.fetchAuthoritativeProfile("shared-token"),
      auth.fetchAuthoritativeProfile("shared-token"),
    ]);

    assert.equal(callCount, 1);
    assert.deepEqual(p1, p2);
  });

  test("7. In-flight login prevents concurrent restoreSession from calling logout", async () => {
    let delayedResolve;
    const fetchPromise = new Promise((resolve) => {
      delayedResolve = resolve;
    });

    const mockFetch = async () => {
      await fetchPromise;
      return {
        status: 200,
        ok: true,
        json: async () => ({
          has_profile: true,
          role: "patient",
          full_name: "Sarah Jenkins",
        }),
      };
    };

    const mockSupabase = {
      auth: {
        signInWithPassword: async () => ({
          data: {
            session: { access_token: "slow-token", user: { id: "u1", email: "test@test.com" } },
          },
          error: null,
        }),
        getSession: async () => ({
          data: { session: null }, // If restoreSession ran now, it would logout!
          error: new Error("Simulated race getSession empty"),
        }),
        signOut: async () => {},
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);

    // Start login
    const loginPromise = auth.loginWithCredentials("test@test.com", "Password123!");
    assert.equal(auth.getIsLoggingIn(), true);

    // Concurrent restoreSession fired by auth state change
    const restored = await auth.restoreSession();
    // restoreSession should immediately return without calling logout
    assert.equal(auth.logoutCallCount, 0);

    // Complete login
    delayedResolve();
    const loggedIn = await loginPromise;
    assert.equal(loggedIn.role, "patient");
    assert.equal(auth.logoutCallCount, 0);
  });

  test("8. Session restoration succeeds after refreshing the page", async () => {
    const mockFetch = async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        has_profile: true,
        role: "doctor",
        full_name: "Dr. Anita Menon, MD",
        email: "doctor@example.com",
        profile_id: "prof_doc_1",
      }),
    });

    const mockSupabase = {
      auth: {
        getSession: async () => ({
          data: {
            session: {
              access_token: "valid-restored-token",
              user: { id: "u_doc_1", email: "doctor@example.com" },
            },
          },
          error: null,
        }),
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);
    const restoredUser = await auth.restoreSession();

    assert.ok(restoredUser);
    assert.equal(restoredUser.role, "doctor");
    assert.equal(restoredUser.name, "Dr. Anita Menon, MD");
    assert.equal(localStorage.getItem(TOKEN_STORAGE_KEY), "valid-restored-token");
  });

  test("9. Unregistered account is handled safely without granting privileges", async () => {
    const mockFetch = async () => ({
      status: 200,
      ok: true,
      json: async () => ({
        has_profile: false,
        role: "unregistered",
        full_name: "New Visitor",
        email: "unregistered@example.com",
      }),
    });

    const mockSupabase = {
      auth: {
        signInWithPassword: async () => ({
          data: {
            session: {
              access_token: "unreg-token",
              user: { id: "u_unreg_1", email: "unregistered@example.com" },
            },
          },
          error: null,
        }),
      },
    };

    const auth = new AuthServiceTest(mockFetch, mockSupabase);
    const user = await auth.loginWithCredentials("unregistered@example.com", "Password123!");

    assert.equal(user.role, "unregistered");
    assert.notEqual(user.role, "patient");
    assert.notEqual(user.role, "admin");
    assert.notEqual(user.role, "doctor");
  });
});
