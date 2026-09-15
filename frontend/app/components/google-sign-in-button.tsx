"use client";

// Real Google Identity Services integration - renders nothing if
// NEXT_PUBLIC_GOOGLE_CLIENT_ID isn't set, so the rest of the app never
// depends on it being configured. When it is set, this loads Google's
// own script and renders their button; the ID token it produces goes
// straight to POST /api/v1/auth/google, which verifies it server-side
// (app/services/tenant_registration_service.py) - this component never
// makes an authentication decision itself, it only collects the token.

import { useEffect, useRef } from "react";
import * as api from "@/lib/api";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: {
            client_id: string;
            callback: (response: { credential: string }) => void;
          }) => void;
          renderButton: (parent: HTMLElement, options: { theme: string; size: string }) => void;
        };
      };
    };
  }
}

export function GoogleSignInButton({
  onSuccess,
  onError,
}: {
  onSuccess: (result: api.TokenResponse) => void;
  onError: (message: string) => void;
}) {
  const buttonRef = useRef<HTMLDivElement>(null);
  const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (!clientId || !buttonRef.current) return;

    const scriptId = "google-identity-services";
    if (!document.getElementById(scriptId)) {
      const script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = renderButton;
      document.head.appendChild(script);
    } else {
      renderButton();
    }

    function renderButton() {
      if (!window.google || !buttonRef.current) return;
      window.google.accounts.id.initialize({
        client_id: clientId!,
        callback: async (response) => {
          try {
            const result = await api.loginWithGoogle(response.credential);
            onSuccess(result);
          } catch (err) {
            onError(err instanceof api.ApiError ? err.message : "Google sign-in failed.");
          }
        },
      });
      window.google.accounts.id.renderButton(buttonRef.current, {
        theme: "outline",
        size: "large",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientId]);

  if (!clientId) return null;
  return <div ref={buttonRef} className="flex justify-center" />;
}
