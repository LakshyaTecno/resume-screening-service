"use client";

import { use, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

function CandidateDetailContent({ candidateId }: { candidateId: string }) {
  const { token } = useAuth();
  const [candidate, setCandidate] = useState<api.Candidate | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;

    let cancelled = false;
    function load() {
      api
        .getCandidate(token!, candidateId)
        .then((result) => {
          if (cancelled) return;
          setCandidate(result);
          // Still processing - poll again shortly. This is the exact
          // "GET /candidates/{id}, watch status" contract the README
          // documents for the async upload pipeline.
          if (["pending", "processing"].includes(result.status)) {
            setTimeout(load, 3000);
          }
        })
        .catch((err) => {
          if (!cancelled) setError(err instanceof api.ApiError ? err.message : "Failed to load.");
        });
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [token, candidateId]);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!candidate) return <p className="text-sm text-black/60 dark:text-white/60">Loading...</p>;

  if (candidate.status !== "processed") {
    return (
      <div>
        <h1 className="text-xl font-semibold mb-2">
          {candidate.full_name || "Resume processing"}
        </h1>
        <p className="text-sm text-black/60 dark:text-white/60">
          Status: <span className="font-medium">{candidate.status}</span>
          {["pending", "processing"].includes(candidate.status) && " - checking again shortly..."}
        </p>
        {candidate.status === "failed" && (
          <p className="text-sm text-red-600 mt-2">
            This resume couldn&apos;t be parsed - the file may be unreadable or contain no
            extractable text.
          </p>
        )}
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-semibold">{candidate.full_name}</h1>
      <p className="text-sm text-black/60 dark:text-white/60">
        {[candidate.email, candidate.phone].filter(Boolean).join(" · ")}
      </p>

      {candidate.summary && <p className="mt-4 text-sm">{candidate.summary}</p>}

      {candidate.skills.length > 0 && (
        <p className="mt-4 text-sm">
          <span className="font-medium">Skills: </span>
          {candidate.skills.join(", ")}
        </p>
      )}

      {candidate.experience.length > 0 && (
        <div className="mt-4">
          <h2 className="font-medium text-sm mb-2">Experience</h2>
          <ul className="space-y-2">
            {candidate.experience.map((exp, i) => (
              <li key={i} className="text-sm">
                <span className="font-medium">{exp.title}</span> at {exp.company}
                {exp.start_date && (
                  <span className="text-black/60 dark:text-white/60">
                    {" "}
                    ({exp.start_date} - {exp.end_date || "Present"})
                  </span>
                )}
                {exp.description && <p className="text-black/70 dark:text-white/70">{exp.description}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {candidate.education.length > 0 && (
        <div className="mt-4">
          <h2 className="font-medium text-sm mb-2">Education</h2>
          <ul className="space-y-1">
            {candidate.education.map((edu, i) => (
              <li key={i} className="text-sm">
                {edu.degree}, {edu.institution}
                {edu.graduation_year && ` (${edu.graduation_year})`}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default function CandidateDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <RequireAuth>
      <CandidateDetailContent candidateId={id} />
    </RequireAuth>
  );
}
