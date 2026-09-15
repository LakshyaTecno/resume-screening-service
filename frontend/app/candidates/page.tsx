"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

const cardClass = "rounded-lg border border-black/10 dark:border-white/10 p-4";
const buttonClass =
  "rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";

const statusColor: Record<api.Candidate["status"], string> = {
  pending: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300",
  processing: "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
  processed: "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
};

function CandidatesContent() {
  const { token } = useAuth();
  const [candidates, setCandidates] = useState<api.Candidate[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function loadCandidates() {
    if (!token) return;
    api
      .listCandidates(token)
      .then(setCandidates)
      .catch((err) => setError(err instanceof api.ApiError ? err.message : "Failed to load."))
      .finally(() => setIsLoading(false));
  }

  useEffect(loadCandidates, [token]);

  // Any candidate still pending/processing means a poll is worth doing -
  // matches the same "poll GET /candidates/{id}" contract the README
  // documents for the API, just applied across the whole list here.
  useEffect(() => {
    const stillWorking = candidates.some((c) => ["pending", "processing"].includes(c.status));
    if (!stillWorking) return;
    const interval = setInterval(loadCandidates, 4000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidates, token]);

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file || !token) return;
    setError(null);
    setIsUploading(true);
    try {
      await api.uploadResume(token, file);
      if (fileInputRef.current) fileInputRef.current.value = "";
      loadCandidates();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Candidates</h1>

      <div className={`${cardClass} mb-8 flex items-center gap-3`}>
        <input ref={fileInputRef} type="file" accept="application/pdf" className="text-sm" />
        <button onClick={handleUpload} disabled={isUploading} className={buttonClass}>
          {isUploading ? "Uploading..." : "Upload resume (PDF)"}
        </button>
      </div>
      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      {isLoading ? (
        <p className="text-sm text-black/60 dark:text-white/60">Loading...</p>
      ) : candidates.length === 0 ? (
        <p className="text-sm text-black/60 dark:text-white/60">No candidates yet.</p>
      ) : (
        <ul className="space-y-3">
          {candidates.map((c) => (
            <li key={c.id} className={`${cardClass} flex items-center justify-between`}>
              <div>
                <Link href={`/candidates/${c.id}`} className="font-medium hover:underline">
                  {c.full_name || "Processing..."}
                </Link>
                {c.email && (
                  <span className="text-sm text-black/60 dark:text-white/60"> · {c.email}</span>
                )}
              </div>
              <span className={`text-xs px-2 py-1 rounded-full ${statusColor[c.status]}`}>
                {c.status}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function CandidatesPage() {
  return (
    <RequireAuth>
      <CandidatesContent />
    </RequireAuth>
  );
}
