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
    <nav className="px-8 py-5">
      <div className="mx-auto flex max-w-5xl items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-violet-500" />
          <span className="text-base font-semibold tracking-tight text-neutral-900">
            Chameleon
          </span>
        </Link>

        <div className="flex items-center gap-6">
          {isCreator && (
            <>
              <Link
                to="/dashboard"
                className="text-sm text-neutral-400 transition-colors hover:text-neutral-900"
              >
                My Videos
              </Link>
              <Link
                to="/upload"
                className="text-sm text-neutral-400 transition-colors hover:text-neutral-900"
              >
                Upload
              </Link>
            </>
          )}
          {isCompany && (
            <Link
              to="/browse"
              className="text-sm text-neutral-400 transition-colors hover:text-neutral-900"
            >
              Browse
            </Link>
          )}

          <Avatar className="h-7 w-7">
            <AvatarImage src={user?.picture} alt={user?.name} />
            <AvatarFallback className="text-xs">
              {user?.name?.slice(0, 2).toUpperCase() ?? "U"}
            </AvatarFallback>
          </Avatar>

          <button
            className="text-neutral-300 transition-colors hover:text-neutral-600"
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
