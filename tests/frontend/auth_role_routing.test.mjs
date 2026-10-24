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

describe("Authentication Role Routing & Unregistered Safeguards", () => {
  const AUTH_STORAGE_KEY = "careroute_user_session";
  const TOKEN_STORAGE_KEY = "careroute_auth_token";

  // Replicate AuthService contract from src/services/auth/index.ts
  class TestAuthService {
    constructor(backendMock) {
      this.backendMock = backendMock;
      this.currentUser = null;
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
      const res = await this.backendMock.fetchMe(token);

      if (res.status === 401) {
        throw new Error("AUTHENTICATION_EXPIRED");
      }

      if (!res.ok) {
        throw new Error(
          `Server error: Failed to verify account role with backend (status ${res.status}).`
        );
      }

      const me = res.data;
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
        };
      }

      return {
        role: "unregistered",
        hasProfile: false,
        fullName: me.full_name,
        email: me.email,
        profileId: undefined,
      };
    }

    async loginWithCredentials(email, password) {
      const authSession = await this.backendMock.signInWithPassword(email, password);
      if (!authSession || !authSession.access_token) {
        throw new Error("Invalid email or password");
      }

      const token = authSession.access_token;
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

      const fullName =
        authResult.fullName ||
        authSession.user?.user_metadata?.full_name ||
        email;

      const user = {
        id: authSession.user.id,
        email: authSession.user.email || email,
        name: fullName,
        role: authResult.role,
        createdAt: authSession.user.created_at || new Date().toISOString(),
      };

      this.currentUser = user;
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
      return user;
    }

    async restoreSession() {
      const session = await this.backendMock.getSession();
      if (!session || !session.access_token) {
        await this.logout();
        return null;
      }

      const token = session.access_token;
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

      const fullName =
        authResult.fullName ||
        session.user?.user_metadata?.full_name ||
        session.user?.email ||
        "User";

      const user = {
        id: session.user.id,
        email: session.user.email || "",
        name: fullName,
        role: authResult.role,
        createdAt: session.user.created_at || new Date().toISOString(),
      };

      this.currentUser = user;
      localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
      return user;
    }

    async logout() {
      this.currentUser = null;
      localStorage.removeItem(AUTH_STORAGE_KEY);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  }

  // Replicate router and AuthContext routing logic
  class MockRouter {
    constructor() {
      this.currentRoute = null;
      this.history = [];
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

  function resolveWorkspaceRoute(user) {
    if (!user) return "/login";
    if (user.role === "patient") return "/patient/dashboard";
    if (user.role === "doctor") return "/doctor/dashboard";
    if (user.role === "admin") return "/admin/dashboard";
    if (user.role === "unregistered") return "/account-setup";
    return "/login";
  }

  beforeEach(() => {
    global.localStorage.clear();
    global.sessionStorage.clear();
  });

  test("1. Admin login redirects to /admin/dashboard", async () => {
    const backendMock = {
      signInWithPassword: async (email, password) => ({
        access_token: "mock-admin-token",
        user: { id: "admin-uuid-1", email: "admin@gmail.com", user_metadata: { full_name: "Admin" } },
      }),
      fetchMe: async (token) => {
        assert.equal(token, "mock-admin-token");
        return {
          ok: true,
          status: 200,
          data: {
            auth_user_id: "admin-uuid-1",
            has_profile: true,
            role: "admin",
            profile_id: "prof-admin-1",
            email: "admin@gmail.com",
            full_name: "Admin",
            is_active: true,
          },
        };
      },
    };

    const authService = new TestAuthService(backendMock);
    const router = new MockRouter();

    const loggedIn = await authService.loginWithCredentials("admin@gmail.com", "valid-password");
    assert.equal(loggedIn.role, "admin");
    assert.equal(loggedIn.email, "admin@gmail.com");

    const destination = resolveWorkspaceRoute(loggedIn);
    router.push(destination);
    assert.equal(router.currentRoute, "/admin/dashboard");
    assert.notEqual(router.currentRoute, "/patient/dashboard");
  });

  test("2. Doctor login redirects to the existing doctor dashboard (/doctor/dashboard)", async () => {
    const backendMock = {
      signInWithPassword: async (email, password) => ({
        access_token: "mock-doc-token",
        user: { id: "doc-uuid-1", email: "dr.menon@careroute.org", user_metadata: { full_name: "Dr. Anita Menon" } },
      }),
      fetchMe: async (token) => {
        assert.equal(token, "mock-doc-token");
        return {
          ok: true,
          status: 200,
          data: {
            auth_user_id: "doc-uuid-1",
            has_profile: true,
            role: "doctor",
            profile_id: "prof-doc-1",
            email: "dr.menon@careroute.org",
            full_name: "Dr. Anita Menon",
            is_active: true,
          },
        };
      },
    };

    const authService = new TestAuthService(backendMock);
    const router = new MockRouter();

    const loggedIn = await authService.loginWithCredentials("dr.menon@careroute.org", "valid-password");
    assert.equal(loggedIn.role, "doctor");

    const destination = resolveWorkspaceRoute(loggedIn);
    router.push(destination);
    assert.equal(router.currentRoute, "/doctor/dashboard");
  });

  test("3. Patient login redirects to /patient/dashboard", async () => {
    const backendMock = {
      signInWithPassword: async (email, password) => ({
        access_token: "mock-pat-token",
        user: { id: "pat-uuid-1", email: "patient@example.com", user_metadata: { full_name: "Sarah Jenkins" } },
      }),
      fetchMe: async (token) => {
        assert.equal(token, "mock-pat-token");
        return {
          ok: true,
          status: 200,
          data: {
            auth_user_id: "pat-uuid-1",
            has_profile: true,
            role: "patient",
            profile_id: "prof-pat-1",
            email: "patient@example.com",
            full_name: "Sarah Jenkins",
            is_active: true,
          },
        };
      },
    };

    const authService = new TestAuthService(backendMock);
    const router = new MockRouter();

    const loggedIn = await authService.loginWithCredentials("patient@example.com", "valid-password");
    assert.equal(loggedIn.role, "patient");

    const destination = resolveWorkspaceRoute(loggedIn);
    router.push(destination);
    assert.equal(router.currentRoute, "/patient/dashboard");
  });

  test("4. An unregistered user is not assigned the patient role", async () => {
    // Backend returns has_profile: false and role: "unregistered"
    const backendMock = {
      signInWithPassword: async (email, password) => ({
        access_token: "mock-unregistered-token",
        user: { id: "unregistered-uuid-1", email: "newuser@example.com" },
      }),
      fetchMe: async (token) => ({
        ok: true,
        status: 200,
        data: {
          auth_user_id: "unregistered-uuid-1",
          has_profile: false,
          role: "unregistered",
          profile_id: null,
          email: "newuser@example.com",
          is_active: true,
        },
      }),
    };

    const authService = new TestAuthService(backendMock);
    const router = new MockRouter();

    const loggedIn = await authService.loginWithCredentials("newuser@example.com", "secret");

    // Strictly ensure no fallback to "patient"
    assert.equal(loggedIn.role, "unregistered");
    assert.notEqual(loggedIn.role, "patient");
    assert.notEqual(loggedIn.role, "admin");
    assert.notEqual(loggedIn.role, "doctor");

    // Verify localStorage does not store "patient" role
    const stored = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY));
    assert.equal(stored.role, "unregistered");

    // Verify routing destination is /account-setup, NOT /patient/dashboard
    const destination = resolveWorkspaceRoute(loggedIn);
    router.push(destination);
    assert.equal(router.currentRoute, "/account-setup");
    assert.notEqual(router.currentRoute, "/patient/dashboard");
    assert.notEqual(router.currentRoute, "/patient/find-care");
  });

  test("5. A restored unregistered session remains unregistered", async () => {
    const backendMock = {
      getSession: async () => ({
        access_token: "mock-unregistered-session-token",
        user: { id: "unregistered-uuid-2", email: "pending.staff@example.com" },
      }),
      fetchMe: async (token) => ({
        ok: true,
        status: 200,
        data: {
          auth_user_id: "unregistered-uuid-2",
          has_profile: false,
          role: "unregistered",
          profile_id: null,
          email: "pending.staff@example.com",
          is_active: true,
        },
      }),
    };

    const authService = new TestAuthService(backendMock);
    const router = new MockRouter();

    const restored = await authService.restoreSession();
    assert.ok(restored);
    assert.equal(restored.role, "unregistered");
    assert.equal(restored.email, "pending.staff@example.com");

    // Session remains unregistered in storage
    const stored = JSON.parse(localStorage.getItem(AUTH_STORAGE_KEY));
    assert.equal(stored.role, "unregistered");

    // Router directs restored session to /account-setup
    const destination = resolveWorkspaceRoute(restored);
    router.replace(destination);
    assert.equal(router.currentRoute, "/account-setup");
  });

  test("6. Role-resolution errors do not grant a default role", async () => {
    // Simulate backend 500 error during role resolution
    const backendMock500 = {
      signInWithPassword: async () => ({
        access_token: "mock-token-error",
        user: { id: "uuid-err", email: "test@example.com" },
      }),
      fetchMe: async () => ({
        ok: false,
        status: 500,
        data: { detail: "Internal database connection failure" },
      }),
    };

    const authService1 = new TestAuthService(backendMock500);

    // loginWithCredentials must throw and MUST NOT grant "patient"
    await assert.rejects(
      async () => {
        await authService1.loginWithCredentials("test@example.com", "password");
      },
      (err) => {
        assert.match(err.message, /Failed to verify account role with backend/i);
        return true;
      }
    );

    // No user or role granted
    assert.equal(authService1.getCurrentUser(), null);
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null);

    // Simulate network error during session restore
    const backendMockNetworkError = {
      getSession: async () => ({
        access_token: "mock-token-net-err",
        user: { id: "uuid-net-err", email: "net@example.com" },
      }),
      fetchMe: async () => {
        throw new Error("Network error: Unable to reach the authentication server");
      },
    };

    const authService2 = new TestAuthService(backendMockNetworkError);

    await assert.rejects(
      async () => {
        await authService2.restoreSession();
      },
      (err) => {
        assert.match(err.message, /Network error/i);
        return true;
      }
    );

    // Session must not be granted any default role
    assert.equal(authService2.getCurrentUser(), null);
    assert.equal(localStorage.getItem(AUTH_STORAGE_KEY), null);
  });
});
