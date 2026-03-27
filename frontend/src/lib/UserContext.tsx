"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { getAccessToken } from "@/lib/auth";
import { api } from "@/lib/api";

export type MeUser = {
  id: string;
  username: string;
  email: string;
  profile_name: string;
  credits_balance: number;
  paid_access: boolean;
  is_admin: boolean;
};

const UserContext = createContext<{
  user: MeUser | null;
  loading: boolean;
  refetch: () => Promise<void>;
}>({ user: null, loading: true, refetch: async () => {} });

export function UserProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<MeUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refetch = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    let lastErr: unknown = null;
    let me: Awaited<ReturnType<typeof api.me>> | null = null;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        me = await api.me();
        lastErr = null;
        break;
      } catch (e) {
        lastErr = e;
        if (attempt < 2) {
          await new Promise((r) => setTimeout(r, 350 * (attempt + 1)));
        }
      }
    }
    setUser(
      me
        ? {
            ...me,
            profile_name: me.profile_name ?? "",
            paid_access: me.paid_access ?? false,
            is_admin: Boolean(me.is_admin),
          }
        : null
    );
    if (lastErr && !me) {
      console.warn("api.me failed after retries", lastErr);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refetch();
    const onAuthChange = () => refetch();
    window.addEventListener("narrative:auth-change", onAuthChange);
    return () => window.removeEventListener("narrative:auth-change", onAuthChange);
  }, [refetch]);

  return (
    <UserContext.Provider value={{ user, loading, refetch }}>
      {children}
    </UserContext.Provider>
  );
}

export function useUser() {
  return useContext(UserContext);
}
