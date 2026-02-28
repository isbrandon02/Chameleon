import { useAuth0 } from "@auth0/auth0-react";
import { LogOut } from "lucide-react";
import { Link } from "react-router-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function Navbar() {
  const { user, logout } = useAuth0();
  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map((r) =>
    r.toLowerCase()
  );
  const isCreator = roles.includes("creator");
  const isCompany = roles.includes("company");

  return (
    <nav className="px-8 py-5 border-b border-white/5">
      <div className="mx-auto flex max-w-6xl items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cham-green/15">
            <span className="text-sm">🦎</span>
          </div>
          <span className="text-base font-semibold tracking-tight text-white">
            Chameleon
          </span>
        </Link>

        <div className="flex items-center gap-6">
          {isCreator && (
            <>
              <Link
                to="/dashboard"
                className="text-sm text-white/40 transition-colors hover:text-cham-green"
              >
                My Videos
              </Link>
              <Link
                to="/upload"
                className="text-sm text-white/40 transition-colors hover:text-cham-green"
              >
                Upload
              </Link>
            </>
          )}
          {isCompany && (
            <Link
              to="/browse"
              className="text-sm text-white/40 transition-colors hover:text-cham-green"
            >
              Browse
            </Link>
          )}

          <Avatar className="h-7 w-7 ring-1 ring-white/10">
            <AvatarImage src={user?.picture} alt={user?.name} />
            <AvatarFallback className="bg-cham-green/10 text-xs text-cham-green">
              {user?.name?.slice(0, 2).toUpperCase() ?? "U"}
            </AvatarFallback>
          </Avatar>

          <button
            className="text-white/20 transition-colors hover:text-white/60"
            onClick={() =>
              logout({ logoutParams: { returnTo: window.location.origin } })
            }
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </nav>
  );
}
