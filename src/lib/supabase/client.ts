import { createClient, SupabaseClient } from "@supabase/supabase-js";

let supabaseInstance: SupabaseClient | null = null;

export function getSupabaseConfigStatus(): {
  configured: boolean;
  missingOrPlaceholder: string[];
} {
  const missingOrPlaceholder: string[] = [];
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!supabaseUrl || supabaseUrl.includes("placeholder-project") || supabaseUrl.includes("your-project")) {
    missingOrPlaceholder.push("NEXT_PUBLIC_SUPABASE_URL");
  }
  if (!supabaseAnonKey || supabaseAnonKey.includes("placeholder-anon-key") || supabaseAnonKey.includes("your-anon-key")) {
    missingOrPlaceholder.push("NEXT_PUBLIC_SUPABASE_ANON_KEY");
  }

  return {
    configured: missingOrPlaceholder.length === 0,
    missingOrPlaceholder,
  };
}

export function isSupabaseConfigured(): boolean {
  return getSupabaseConfigStatus().configured;
}

export function getSupabaseClient(): SupabaseClient | null {
  const status = getSupabaseConfigStatus();

  if (!status.configured) {
    if (process.env.NODE_ENV === "production") {
      throw new Error(
        `FATAL: Production build cannot start with missing or placeholder Supabase configuration: [${status.missingOrPlaceholder.join(
          ", "
        )}]`
      );
    }
    return null;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

  if (!supabaseInstance) {
    supabaseInstance = createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
  }

  return supabaseInstance;
}

