import { useAuth0 } from "@auth0/auth0-react";
import { ReactNode } from "react";
import { Navigate } from "react-router-dom";

const ROLES_CLAIM = "https://chameleon.com/roles";

interface Props {
  children: ReactNode;
  requiredRole?: "creator" | "company";
}

export default function ProtectedRoute({ children, requiredRole }: Props) {
  const { isAuthenticated, isLoading, loginWithRedirect, user } = useAuth0();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    loginWithRedirect({ appState: { returnTo: window.location.pathname } });
    return null;
  }

  if (requiredRole) {
    const auth0Roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map(
      (r) => r.toLowerCase()
    );
    const storedRole = localStorage.getItem("pendingRole") ?? "";
    const hasRole = (r: string) => auth0Roles.includes(r) || storedRole === r;

    if (!hasRole(requiredRole)) {
      if (hasRole("creator")) return <Navigate to="/dashboard" replace />;
      if (hasRole("company")) return <Navigate to="/browse" replace />;
      return <Navigate to="/" replace />;
    }
  }

  return <>{children}</>;
}
