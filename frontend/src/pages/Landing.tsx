import { useAuth0 } from "@auth0/auth0-react";
import { ArrowRight, Video, Building2 } from "lucide-react";
import { Navigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
    <div className="flex min-h-screen flex-col">
      {/* Hero */}
      <header className="border-b px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-xl font-bold">Chameleon</span>
          <Button
            variant="ghost"
            onClick={() => loginWithRedirect()}
          >
            Sign in
          </Button>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 py-20 text-center">
        <h1 className="mb-4 text-5xl font-extrabold tracking-tight">
          Sponsorships, matched by AI
        </h1>
        <p className="mb-10 max-w-xl text-lg text-muted-foreground">
          Chameleon connects creators with brands through automated video
          analysis — no back-and-forth emails, just the right deal at the right
          time.
        </p>

        <div className="flex flex-col gap-4 sm:flex-row">
          <Card className="w-72 text-left">
            <CardHeader>
              <Video className="mb-2 h-8 w-8" />
              <CardTitle>I'm a Creator</CardTitle>
              <CardDescription>
                Upload your videos. Our AI analyzes content and topics so
                brands can find you.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                className="w-full"
                onClick={() =>
                  (localStorage.setItem("pendingRole", "creator"),
                  loginWithRedirect({
                    appState: { returnTo: "/dashboard" },
                    authorizationParams: { screen_hint: "signup", user_type: "creator" },
                  }))
                }
              >
                Join as Creator <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </Card>

          <Card className="w-72 text-left">
            <CardHeader>
              <Building2 className="mb-2 h-8 w-8" />
              <CardTitle>I'm a Company</CardTitle>
              <CardDescription>
                Browse AI-analyzed videos and make sponsorship offers to the
                creators that fit your brand.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button
                className="w-full"
                variant="outline"
                onClick={() =>
                  (localStorage.setItem("pendingRole", "company"),
                  loginWithRedirect({
                    appState: { returnTo: "/browse" },
                    authorizationParams: { screen_hint: "signup", user_type: "company" },
                  }))
                }
              >
                Join as Company <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
