"use client";

import { useEffect, useState, FormEvent } from "react";
import Link from "next/link";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

const inputClass =
  "w-full rounded-md border border-black/15 dark:border-white/15 bg-transparent px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500";
const buttonClass =
  "rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";
const cardClass = "rounded-lg border border-black/10 dark:border-white/10 p-4";

function JobsContent() {
  const { token } = useAuth();
  const [jobs, setJobs] = useState<api.Job[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [description, setDescription] = useState("");
  const [requiredSkills, setRequiredSkills] = useState("");
  const [preferredSkills, setPreferredSkills] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  function loadJobs() {
    if (!token) return;
    setIsLoading(true);
    api
      .listJobs(token)
      .then(setJobs)
      .catch((err) => setError(err instanceof api.ApiError ? err.message : "Failed to load."))
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    // Fetch-on-mount/token-change - the standard data-fetching effect
    // pattern, just extracted into loadJobs so the create-job form can
    // also call it to refresh the list after a successful POST.
    /* eslint-disable-next-line react-hooks/set-state-in-effect */
    loadJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await api.createJob(token, {
        title,
        company: company || undefined,
        description,
        required_skills: requiredSkills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        preferred_skills: preferredSkills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setTitle("");
      setCompany("");
      setDescription("");
      setRequiredSkills("");
      setPreferredSkills("");
      loadJobs();
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Failed to create job.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold mb-6">Jobs</h1>

      <form onSubmit={handleSubmit} className={`${cardClass} space-y-3 mb-8`}>
        <h2 className="font-medium text-sm">Create a job posting</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input
            placeholder="Title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputClass}
          />
          <input
            placeholder="Company (optional)"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            className={inputClass}
          />
        </div>
        <textarea
          placeholder="Description"
          required
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className={inputClass}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input
            placeholder="Required skills, comma separated"
            value={requiredSkills}
            onChange={(e) => setRequiredSkills(e.target.value)}
            className={inputClass}
          />
          <input
            placeholder="Preferred skills, comma separated"
            value={preferredSkills}
            onChange={(e) => setPreferredSkills(e.target.value)}
            className={inputClass}
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button type="submit" disabled={isSubmitting} className={buttonClass}>
          {isSubmitting ? "Creating..." : "Create job"}
        </button>
      </form>

      {isLoading ? (
        <p className="text-sm text-black/60 dark:text-white/60">Loading...</p>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-black/60 dark:text-white/60">No jobs yet.</p>
      ) : (
        <ul className="space-y-3">
          {jobs.map((job) => (
            <li key={job.id} className={cardClass}>
              <Link href={`/jobs/${job.id}`} className="font-medium hover:underline">
                {job.title}
              </Link>
              {job.company && (
                <span className="text-sm text-black/60 dark:text-white/60"> · {job.company}</span>
              )}
              <p className="text-sm text-black/60 dark:text-white/60 mt-1 line-clamp-2">
                {job.description}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function JobsPage() {
  return (
    <RequireAuth>
      <JobsContent />
    </RequireAuth>
  );
}
