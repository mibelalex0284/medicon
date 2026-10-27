"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function RootPage() {
  const { user, isLoading, authError, refreshSession } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      if (!user) {
        if (!authError) {
          router.replace("/login");
        }
      } else if (user.role === "patient") {
        router.replace("/patient/dashboard");
      } else if (user.role === "doctor") {
        router.replace("/doctor/dashboard");
      } else if (user.role === "admin") {
        router.replace("/admin/dashboard");
      } else if (user.role === "unregistered") {
        router.replace("/account-setup");
      } else {
        router.replace("/login");
      }
    }
  }, [user, isLoading, authError, router]);

  if (authError && !user && !isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
        <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-6 text-center border border-slate-200">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 text-amber-600 mb-4">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900 mb-2">Role Verification Error</h2>
          <p className="text-sm text-slate-600 mb-6">{authError}</p>
          <div className="flex justify-center gap-3">
            <Button
              onClick={() => refreshSession()}
              variant="outline"
              className="flex items-center gap-2 border-slate-300"
            >
              <RefreshCw className="h-4 w-4" />
              Retry Verification
            </Button>
            <Button
              onClick={() => router.push("/login")}
              className="bg-sky-600 hover:bg-sky-700 text-white"
            >
              Return to Sign In
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <div className="flex flex-col items-center gap-3">
        <div className="h-9 w-9 animate-spin rounded-full border-3 border-sky-600 border-t-transparent" />
        <p className="text-xs text-slate-500 font-medium tracking-wide">
          Connecting to MediLink...
        </p>
      </div>
    </div>
  );
}
