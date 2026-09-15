"use client";

// JWT held in memory + localStorage, client-side only. A real product
// would want httpOnly cookies and refresh-token rotation instead of a
// long-lived token sitting in localStorage (readable by any script on
// the page) - this is a deliberate, named simplification matching the
// scope of this project, not an oversight. See README.md's frontend
// section for the same point made explicitly.

import { createContext, useContext, useEffect, useState, ReactNode } from "react";

const STORAGE_KEY = "resume_screening_token";

interface AuthContextValue {
  token: string | null;
  tenantId: string | null;
  isLoading: boolean;
  login: (token: string, tenantId: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [tenantId, setTenantId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // One-time hydration from localStorage on mount - localStorage isn't
    // available during SSR, so this can't run any earlier than an effect,
    // and there's no external subscription to attach here instead.
    /* eslint-disable react-hooks/set-state-in-effect */
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setToken(parsed.token);
        setTenantId(parsed.tenantId);
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
    setIsLoading(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, []);

  function login(newToken: string, newTenantId: string) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ token: newToken, tenantId: newTenantId }));
    setToken(newToken);
    setTenantId(newTenantId);
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setTenantId(null);
  }

  return (
    <AuthContext.Provider value={{ token, tenantId, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
