"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

const cardClass = "rounded-lg border border-black/10 dark:border-white/10 p-6";

function DashboardContent() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<api.Job[] | null>(null);
  const [candidates, setCandidates] = useState<api.Candidate[] | null>(null);
  const [subscription, setSubscription] = useState<api.Subscription | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.listJobs(token), api.listCandidates(token), api.getMySubscription(token)])
      .then(([jobsRes, candidatesRes, subscriptionRes]) => {
        setJobs(jobsRes);
        setCandidates(candidatesRes);
        setSubscription(subscriptionRes);
      })
      .catch((err) => setError(err instanceof api.ApiError ? err.message : "Failed to load."));
  }, [token]);

  const processed = candidates?.filter((c) => c.status === "processed").length ?? 0;
  const pending = candidates?.filter((c) => ["pending", "processing"].includes(c.status)).length ?? 0;

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Dashboard</h1>
      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        <div className={cardClass}>
          <p className="text-sm text-black/60 dark:text-white/60">Jobs</p>
          <p className="text-2xl font-semibold">{jobs?.length ?? "..."}</p>
        </div>
        <div className={cardClass}>
          <p className="text-sm text-black/60 dark:text-white/60">Candidates processed</p>
          <p className="text-2xl font-semibold">{processed}</p>
          {pending > 0 && (
            <p className="text-xs text-black/50 dark:text-white/50 mt-1">{pending} still processing</p>
          )}
        </div>
        <div className={cardClass}>
          <p className="text-sm text-black/60 dark:text-white/60">Plan</p>
          <p className="text-2xl font-semibold">
            {subscription ? subscription.status : "Free tier"}
          </p>
        </div>
      </div>

      <div className="flex gap-4">
        <Link href="/jobs" className="text-blue-600 hover:underline text-sm">
          Manage jobs →
        </Link>
        <Link href="/candidates" className="text-blue-600 hover:underline text-sm">
          Manage candidates →
        </Link>
        <Link href="/billing" className="text-blue-600 hover:underline text-sm">
          Billing →
        </Link>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <RequireAuth>
      <DashboardContent />
    </RequireAuth>
  );
}
