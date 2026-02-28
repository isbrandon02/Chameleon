import { useAuth0 } from "@auth0/auth0-react";
import { ArrowRight } from "lucide-react";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function Landing() {
  const { loginWithRedirect, isAuthenticated, user } = useAuth0();

  if (isAuthenticated && user) {
    const auth0Roles = ((user[ROLES_CLAIM] as string[] | undefined) ?? []).map(
      (r) => r.toLowerCase()
    );
    const role =
      auth0Roles.find((r) => r === "creator" || r === "company") ??
      localStorage.getItem("pendingRole");
    if (role === "creator") return <Navigate to="/dashboard" replace />;
    if (role === "company") return <Navigate to="/browse" replace />;
  }

  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* Navbar */}
      <header className="px-8 py-6">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-violet-500" />
            <span className="text-base font-semibold tracking-tight text-neutral-900">
              Chameleon
            </span>
          </div>
          <button
            className="text-sm text-neutral-400 transition-colors hover:text-neutral-900"
            onClick={() => loginWithRedirect()}
          >
            Sign in
          </button>
        </div>
      </header>

      {/* Hero */}
      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24 pt-16 text-center">
        <h1 className="mb-5 max-w-2xl text-6xl font-bold tracking-tight text-neutral-900">
          Sponsorships,<br />matched by AI
        </h1>
        <p className="mb-12 max-w-md text-base leading-relaxed text-neutral-400">
          Chameleon connects creators with brands through automated video
          analysis — no back-and-forth emails, just the right deal at the right time.
        </p>

        <div className="flex items-center gap-4">
          <Button
            className="h-11 rounded-full bg-neutral-900 px-6 text-sm font-medium text-white hover:bg-neutral-700"
            onClick={() => (
              localStorage.setItem("pendingRole", "creator"),
              loginWithRedirect({
                appState: { returnTo: "/dashboard" },
                authorizationParams: { screen_hint: "signup", user_type: "creator" },
              })
            )}
          >
            Join as Creator <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
          </Button>

          <div className="h-4 w-px bg-neutral-200" />

          <button
            className="text-sm text-neutral-400 transition-colors hover:text-neutral-900"
            onClick={() => (
              localStorage.setItem("pendingRole", "company"),
              loginWithRedirect({
                appState: { returnTo: "/browse" },
                authorizationParams: { screen_hint: "signup", user_type: "company" },
              })
            )}
          >
            I'm a Company <ArrowRight className="ml-1 inline h-3.5 w-3.5" />
          </button>
        </div>
      </main>
    </div>
  );
}
