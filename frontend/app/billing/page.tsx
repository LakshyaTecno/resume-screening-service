"use client";

import { useEffect, useState } from "react";
import * as api from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { RequireAuth } from "@/lib/require-auth";

const cardClass = "rounded-lg border border-black/10 dark:border-white/10 p-4";
const buttonClass =
  "rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50";

function formatPrice(cents: number, currency: string) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency }).format(cents / 100);
}

function BillingContent() {
  const { token } = useAuth();
  const [plans, setPlans] = useState<api.Plan[]>([]);
  const [subscription, setSubscription] = useState<api.Subscription | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [subscribingPlanId, setSubscribingPlanId] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    Promise.all([api.listPlans(token), api.getMySubscription(token)])
      .then(([plansRes, subscriptionRes]) => {
        setPlans(plansRes);
        setSubscription(subscriptionRes);
      })
      .catch((err) => setError(err instanceof api.ApiError ? err.message : "Failed to load."));
  }, [token]);

  async function handleSubscribe(planId: string) {
    if (!token) return;
    setError(null);
    setSubscribingPlanId(planId);
    try {
      const result = await api.subscribe(token, planId);
      // Razorpay's own hosted checkout page - not something this app
      // renders itself, just redirects to.
      // eslint-disable-next-line react-hooks/immutability
      window.location.href = result.checkout_url;
    } catch (err) {
      setError(err instanceof api.ApiError ? err.message : "Subscribe failed.");
      setSubscribingPlanId(null);
    }
  }

  return (
    <div>
      <h1 className="text-xl font-semibold mb-2">Billing</h1>
      <p className="text-sm text-black/60 dark:text-white/60 mb-6">
        {subscription
          ? `Current plan status: ${subscription.status}`
          : "No active subscription - you're on the free tier (limited resumes, see README.md)."}
      </p>
      {error && <p className="text-sm text-red-600 mb-4">{error}</p>}

      {plans.length === 0 ? (
        <p className="text-sm text-black/60 dark:text-white/60">
          No plans configured yet - an admin needs to create one via the Admin API.
        </p>
      ) : (
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {plans.map((plan) => (
            <li key={plan.id} className={cardClass}>
              <h2 className="font-medium">{plan.name}</h2>
              <p className="text-2xl font-semibold mt-1">
                {formatPrice(plan.price, plan.currency)}
                <span className="text-sm font-normal text-black/60 dark:text-white/60">
                  {" "}
                  / {plan.duration_months} mo
                </span>
              </p>
              <p className="text-sm text-black/60 dark:text-white/60 mt-1">
                {plan.monthly_resume_quota
                  ? `${plan.monthly_resume_quota} resumes / month`
                  : "Unlimited resumes"}
              </p>
              <button
                onClick={() => handleSubscribe(plan.id)}
                disabled={subscribingPlanId === plan.id || subscription?.plan_id === plan.id}
                className={`${buttonClass} mt-4 w-full`}
              >
                {subscription?.plan_id === plan.id
                  ? "Current plan"
                  : subscribingPlanId === plan.id
                    ? "Redirecting..."
                    : "Subscribe"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function BillingPage() {
  return (
    <RequireAuth>
      <BillingContent />
    </RequireAuth>
  );
}
