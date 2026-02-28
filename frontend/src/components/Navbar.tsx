import { useAuth0 } from "@auth0/auth0-react";
import { LogOut } from "lucide-react";
import { Link } from "react-router-dom";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function Navbar() {
  const { user, logout } = useAuth0();
  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map((r) =>
    r.toLowerCase()
  );
  const isCreator = roles.includes("creator");
  const isCompany = roles.includes("company");

  return (
    <nav className="border-b border-white/[0.04] px-6 py-5 sm:px-10">
      <div className="mx-auto flex max-w-6xl items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5">
          <img src="/chameleon.png" alt="" className="h-7 w-7 object-contain" />
          <span className="text-[17px] font-semibold tracking-tight text-white">
            chameleon
          </span>
        </Link>

        <div className="flex items-center gap-6">
          {isCreator && (
            <>
              <Link
                to="/dashboard"
                className="text-[14px] font-medium text-white/35 transition-colors hover:text-white"
              >
                My Videos
              </Link>
              <Link
                to="/upload"
                className="text-[14px] font-medium text-white/35 transition-colors hover:text-white"
              >
                Upload
              </Link>
            </>
          )}
          {isCompany && (
            <Link
              to="/browse"
              className="text-[14px] font-medium text-white/35 transition-colors hover:text-white"
            >
              Browse
            </Link>
          )}

          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-white/[0.06] text-[11px] font-semibold text-white/50">
            {user?.name?.slice(0, 2).toUpperCase() ?? "U"}
          </div>

          <button
            className="text-white/20 transition-colors hover:text-white/50"
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
