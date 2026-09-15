// Thin fetch wrapper around the backend API (../app/routers/*.py).
// Every function here maps 1:1 to a real endpoint - no client-side
// business logic duplicated from the backend, this just calls it.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, headers, ...rest } = options;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      ...(rest.body && !(rest.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // Non-JSON error body - fall back to statusText.
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ---- Types (mirrors app/models/schemas.py) ----

export interface TokenResponse {
  access_token: string;
  token_type: string;
  tenant_id: string;
}

export interface ExperienceEntry {
  title: string;
  company: string;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
}

export interface EducationEntry {
  degree: string;
  institution: string;
  graduation_year?: string | null;
}

export interface Candidate {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  summary: string | null;
  skills: string[];
  experience: ExperienceEntry[];
  education: EducationEntry[];
  status: "pending" | "processing" | "processed" | "failed";
  created_at: string;
}

export interface Job {
  id: string;
  title: string;
  company: string | null;
  description: string;
  required_skills: string[];
  preferred_skills: string[];
  created_at: string;
}

export interface RankedCandidate {
  candidate_id: string;
  full_name: string;
  vector_score: number;
  llm_score: number;
  rank: number;
  explanation: string;
  strengths: string[];
  gaps: string[];
}

export interface ScreeningResponse {
  job_id: string;
  job_title: string;
  total_candidates_screened: number;
  ranked_candidates: RankedCandidate[];
}

export interface Plan {
  id: string;
  name: string;
  price: number;
  currency: string;
  monthly_resume_quota: number | null;
  duration_months: number;
  razorpay_plan_id: string;
}

export interface Subscription {
  id: string;
  plan_id: string;
  status: string;
  current_period_end: string | null;
}

// ---- Auth (app/routers/auth.py) ----

export function register(email: string, password: string) {
  return request<TokenResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function login(email: string, password: string) {
  return request<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function loginWithGoogle(idToken: string) {
  return request<TokenResponse>("/api/v1/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
}

// ---- Jobs (app/routers/jobs.py) ----

export function listJobs(token: string) {
  return request<Job[]>("/api/v1/jobs/", { token });
}

export function getJob(token: string, id: string) {
  return request<Job>(`/api/v1/jobs/${id}`, { token });
}

export function createJob(
  token: string,
  payload: {
    title: string;
    company?: string;
    description: string;
    required_skills: string[];
    preferred_skills: string[];
  }
) {
  return request<Job>("/api/v1/jobs/", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

// ---- Candidates (app/routers/candidates.py) ----

export function listCandidates(token: string) {
  return request<Candidate[]>("/api/v1/candidates/", { token });
}

export function getCandidate(token: string, id: string) {
  return request<Candidate>(`/api/v1/candidates/${id}`, { token });
}

export function uploadResume(token: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<Candidate>("/api/v1/candidates/upload", {
    method: "POST",
    token,
    body: formData,
  });
}

// ---- Screening (app/routers/screening.py) ----

export function rankCandidates(
  token: string,
  jobId: string,
  opts?: { top_k?: number; top_n?: number }
) {
  return request<ScreeningResponse>("/api/v1/screening/rank", {
    method: "POST",
    token,
    body: JSON.stringify({ job_id: jobId, ...opts }),
  });
}

// ---- Billing (app/routers/billing.py) ----

export function listPlans(token: string) {
  return request<Plan[]>("/api/v1/billing/plans", { token });
}

export function getMySubscription(token: string) {
  return request<Subscription | null>("/api/v1/billing/subscription", { token });
}

export function subscribe(token: string, planId: string) {
  return request<{ subscription_id: string; status: string; checkout_url: string }>(
    "/api/v1/billing/subscribe",
    { method: "POST", token, body: JSON.stringify({ plan_id: planId }) }
  );
}
