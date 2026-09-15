"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { ReactNode } from "react";
import { useAuth } from "./auth-context";

// Wraps a page's content; redirects to /login if there's no token once
// the initial localStorage read (isLoading) has settled. Renders nothing
// during that brief check to avoid a flash of protected content.
export function RequireAuth({ children }: { children: ReactNode }) {
  const { token, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !token) {
      router.replace("/login");
    }
  }, [isLoading, token, router]);

  if (isLoading || !token) return null;
  return <>{children}</>;
}
