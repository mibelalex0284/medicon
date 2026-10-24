"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { User, UserRole, PatientProfile } from "@/types";
import { authService } from "@/services/auth";
import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

interface AuthContextType {
  user: User | null;
  role: UserRole | null;
  patientProfile: PatientProfile;
  loginWithCredentials: (email: string, password: string) => Promise<User>;
  registerPatient: (payload: {
    full_name: string;
    email: string;
    password: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }) => Promise<User>;
  completePatientProfile: (payload: {
    full_name: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }) => Promise<User>;
  loginAsRole: (role: UserRole) => void;
  logout: () => Promise<void>;
  isLoading: boolean;
  refreshSession: () => Promise<User | null>;
  authError: string | null;
  clearAuthError: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const router = useRouter();

  const clearAuthError = () => setAuthError(null);

  useEffect(() => {
    let isMounted = true;

    async function initAuth() {
      try {
        const restored = await authService.restoreSession();
        if (isMounted) {
          setUser(restored);
          setAuthError(null);
        }
      } catch (err: any) {
        if (isMounted) {
          setUser(null);
          setAuthError(err.message || "Failed to resolve authenticated role permissions.");
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    initAuth();

    // Subscribe to live Supabase auth-state changes if configured
    const supabase = getSupabaseClient();
    let subscription: { unsubscribe: () => void } | null = null;

    if (supabase && isSupabaseConfigured()) {
      const { data } = supabase.auth.onAuthStateChange(async (event, session) => {
        if (event === "SIGNED_OUT") {
          setUser(null);
          localStorage.removeItem("careroute_auth_token");
        } else if (event === "SIGNED_IN" || event === "TOKEN_REFRESHED") {
          if (session?.access_token) {
            localStorage.setItem("careroute_auth_token", session.access_token);
            try {
              const restored = await authService.restoreSession();
              if (isMounted) {
                setUser(restored);
                setAuthError(null);
              }
            } catch (err: any) {
              if (isMounted) {
                setUser(null);
                setAuthError(err.message || "Failed to resolve session permissions");
              }
            }
          }
        }
      });
      subscription = data.subscription;
    }

    return () => {
      isMounted = false;
      if (subscription) {
        subscription.unsubscribe();
      }
    };
  }, []);

  const loginWithCredentials = async (email: string, password: string): Promise<User> => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const loggedIn = await authService.loginWithCredentials(email, password);
      setUser(loggedIn);

      // Route to destination workspace based on verified role
      if (loggedIn.role === "patient") router.push("/patient/dashboard");
      else if (loggedIn.role === "doctor") router.push("/doctor/dashboard");
      else if (loggedIn.role === "admin") router.push("/admin/dashboard");
      else if (loggedIn.role === "unregistered") router.push("/account-setup");

      return loggedIn;
    } catch (err: any) {
      setAuthError(err.message || "Authentication failed");
      throw err;
    } finally {
      setIsLoading(false);
    }
  };

  const registerPatient = async (payload: {
    full_name: string;
    email: string;
    password: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }): Promise<User> => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const registered = await authService.registerPatient(payload);
      setUser(registered);
      router.push("/patient/dashboard");
      return registered;
    } finally {
      setIsLoading(false);
    }
  };

  const completePatientProfile = async (payload: {
    full_name: string;
    date_of_birth: string;
    phone?: string;
    emergency_contact?: string;
    preferred_language?: string;
  }): Promise<User> => {
    setIsLoading(true);
    setAuthError(null);
    try {
      const registered = await authService.completePatientProfile(payload);
      setUser(registered);
      router.push("/patient/dashboard");
      return registered;
    } finally {
      setIsLoading(false);
    }
  };

  const refreshSession = async (): Promise<User | null> => {
    setIsLoading(true);
    try {
      const restored = await authService.restoreSession();
      setUser(restored);
      setAuthError(null);
      return restored;
    } catch (err: any) {
      setAuthError(err.message || "Failed to refresh session");
      return null;
    } finally {
      setIsLoading(false);
    }
  };

  const loginAsRole = (newRole: UserRole) => {
    const loggedIn = authService.loginAsRole(newRole);
    setUser(loggedIn);
    if (newRole === "patient") router.push("/patient/dashboard");
    else if (newRole === "doctor") router.push("/doctor/dashboard");
    else if (newRole === "admin") router.push("/admin/dashboard");
    else if (newRole === "unregistered") router.push("/account-setup");
  };

  const logout = async () => {
    await authService.logout();
    setUser(null);
    setAuthError(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role: user ? user.role : null,
        patientProfile: authService.getPatientProfile(),
        loginWithCredentials,
        registerPatient,
        completePatientProfile,
        loginAsRole,
        logout,
        isLoading,
        refreshSession,
        authError,
        clearAuthError,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
