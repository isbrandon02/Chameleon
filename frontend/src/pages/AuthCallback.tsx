import { useAuth0 } from "@auth0/auth0-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

const ROLES_CLAIM = "https://chameleon.com/roles";

function getEffectiveRole(user: Record<string, unknown>): string | null {
  // Prefer Auth0 RBAC roles if present
  const auth0Roles = ((user[ROLES_CLAIM] as string[] | undefined) ?? []).map(
    (r) => r.toLowerCase()
  );
  if (auth0Roles.includes("creator")) return "creator";
  if (auth0Roles.includes("company")) return "company";

  // Fall back to role chosen on landing page (stored before redirect)
  const pending = localStorage.getItem("pendingRole");
  if (pending === "creator" || pending === "company") return pending;

  return null;
}

export default function AuthCallback() {
  const { handleRedirectCallback, isAuthenticated, isLoading, user } =
    useAuth0();
  const navigate = useNavigate();

  useEffect(() => {
    if (isLoading) return;

    let cancelled = false;

    (async () => {
      let returnTo: string | undefined;
      try {
        const result = await handleRedirectCallback();
        if (cancelled) return;
        returnTo = (result?.appState as { returnTo?: string })?.returnTo;
      } catch {
        // No callback params — user was already authenticated
      }

      if (cancelled) return;

      if (isAuthenticated && user) {
        const role = getEffectiveRole(user as Record<string, unknown>);
        localStorage.removeItem("pendingRole");

        if (returnTo) {
          navigate(returnTo, { replace: true });
        } else {
          navigate(role === "creator" ? "/dashboard" : "/browse", {
            replace: true,
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [isLoading]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
    </div>
  );
}
