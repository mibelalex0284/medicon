"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { User, UserRole, PatientProfile } from "@/types";
import { authService } from "@/services/auth";
import { useRouter } from "next/navigation";

interface AuthContextType {
  user: User | null;
  role: UserRole;
  patientProfile: PatientProfile;
  loginAsRole: (role: UserRole) => void;
  logout: () => void;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const current = authService.getCurrentUser();
    setUser(current);
    setIsLoading(false);
  }, []);

  const loginAsRole = (newRole: UserRole) => {
    const loggedIn = authService.loginAsRole(newRole);
    setUser(loggedIn);
    // Route to appropriate role area
    if (newRole === "patient") router.push("/patient/dashboard");
    else if (newRole === "doctor") router.push("/doctor/dashboard");
    else if (newRole === "admin") router.push("/admin/dashboard");
  };

  const logout = () => {
    authService.logout();
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        role: user?.role || "patient",
        patientProfile: authService.getPatientProfile(),
        loginAsRole,
        logout,
        isLoading,
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
