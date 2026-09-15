"use client";

import { use, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

const cardClass = "rounded-lg border border-black/10 dark:border-white/10 p-4";
const buttonClass =
  "rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";

function JobDetailContent({ jobId }: { jobId: string }) {
  const { token } = useAuth();
  const [job, setJob] = useState<api.Job | null>(null);
  const [results, setResults] = useState<api.ScreeningResponse | null>(null);
  const [isRanking, setIsRanking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .getJob(token, jobId)
      .then(setJob)
      .catch((err) => setError(err instanceof api.ApiError ? err.message : "Failed to load job."));
  }, [token, jobId]);

  async function handleRank() {
    if (!token) return;
    setError(null);
    setIsRanking(true);
    try {
      setResults(await api.rankCandidates(token, jobId));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Ranking failed.");
    } finally {
      setIsRanking(false);
    }
  }

  if (error && !job) return <p className="text-sm text-red-600">{error}</p>;
  if (!job) return <p className="text-sm text-black/60 dark:text-white/60">Loading...</p>;

  return (
    <div>
      <h1 className="text-xl font-semibold">{job.title}</h1>
      {job.company && <p className="text-sm text-black/60 dark:text-white/60">{job.company}</p>}
      <p className="mt-4 text-sm whitespace-pre-wrap">{job.description}</p>

      {job.required_skills.length > 0 && (
        <p className="mt-3 text-sm">
          <span className="font-medium">Required: </span>
          {job.required_skills.join(", ")}
        </p>
      )}
      {job.preferred_skills.length > 0 && (
        <p className="text-sm">
          <span className="font-medium">Preferred: </span>
          {job.preferred_skills.join(", ")}
        </p>
      )}

      <button onClick={handleRank} disabled={isRanking} className={`${buttonClass} mt-6`}>
        {isRanking ? "Ranking..." : "Rank candidates"}
      </button>
      {error && job && <p className="text-sm text-red-600 mt-2">{error}</p>}

      {results && (
        <div className="mt-8">
          <h2 className="font-medium mb-3">
            {results.ranked_candidates.length} of {results.total_candidates_screened} candidates
            screened, ranked
          </h2>
          {results.ranked_candidates.length === 0 ? (
            <p className="text-sm text-black/60 dark:text-white/60">
              No candidates matched closely enough to rank. Upload resumes on the Candidates page
              first.
            </p>
          ) : (
            <ul className="space-y-3">
              {results.ranked_candidates.map((c) => (
                <li key={c.candidate_id} className={cardClass}>
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium">
                      #{c.rank} {c.full_name}
                    </span>
                    <span className="text-sm text-black/60 dark:text-white/60">
                      {c.llm_score.toFixed(0)}/100
                    </span>
                  </div>
                  <p className="text-sm mt-1">{c.explanation}</p>
                  {c.strengths.length > 0 && (
                    <p className="text-xs text-green-700 dark:text-green-400 mt-2">
                      + {c.strengths.join(", ")}
                    </p>
                  )}
                  {c.gaps.length > 0 && (
                    <p className="text-xs text-red-700 dark:text-red-400 mt-1">
                      − {c.gaps.join(", ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <JobDetailContent jobId={id} />
    </RequireAuth>
  );
}
