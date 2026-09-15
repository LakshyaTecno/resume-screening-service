"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

export function NavBar() {
  const { token, logout } = useAuth();
  const router = useRouter();

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav className="border-b border-black/10 dark:border-white/10">
      <div className="mx-auto max-w-5xl flex items-center justify-between px-4 py-3">
        <Link href={token ? "/dashboard" : "/login"} className="font-semibold">
          Resume Screening
        </Link>
        {token && (
          <div className="flex items-center gap-5 text-sm">
            <Link href="/dashboard" className="hover:underline">
              Dashboard
            </Link>
            <Link href="/jobs" className="hover:underline">
              Jobs
            </Link>
            <Link href="/candidates" className="hover:underline">
              Candidates
            </Link>
            <Link href="/billing" className="hover:underline">
              Billing
            </Link>
            <button onClick={handleLogout} className="text-red-600 hover:underline">
              Log out
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}
