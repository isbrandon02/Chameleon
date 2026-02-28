import { useAuth0 } from "@auth0/auth0-react";
import { LogOut, Upload, Video } from "lucide-react";
import { Link } from "react-router-dom";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";

const ROLES_CLAIM = "https://chameleon.com/roles";

export default function Navbar() {
  const { user, logout } = useAuth0();
  const roles = ((user?.[ROLES_CLAIM] as string[] | undefined) ?? []).map((r) =>
    r.toLowerCase()
  );
  const isCreator = roles.includes("creator");
  const isCompany = roles.includes("company");

  return (
    <nav className="border-b bg-background px-6 py-3">
      <div className="mx-auto flex max-w-7xl items-center justify-between">
        <Link to="/" className="text-xl font-bold tracking-tight">
          Chameleon
        </Link>

        <div className="flex items-center gap-4">
          {isCreator && (
            <>
              <Link to="/dashboard">
                <Button variant="ghost" size="sm">
                  <Video className="mr-2 h-4 w-4" />
                  My Videos
                </Button>
              </Link>
              <Link to="/upload">
                <Button variant="ghost" size="sm">
                  <Upload className="mr-2 h-4 w-4" />
                  Upload
                </Button>
              </Link>
            </>
          )}
          {isCompany && (
            <Link to="/browse">
              <Button variant="ghost" size="sm">
                Browse Videos
              </Button>
            </Link>
          )}

          <Avatar className="h-8 w-8">
            <AvatarImage src={user?.picture} alt={user?.name} />
            <AvatarFallback>
              {user?.name?.slice(0, 2).toUpperCase() ?? "U"}
            </AvatarFallback>
          </Avatar>

          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              logout({ logoutParams: { returnTo: window.location.origin } })
            }
          >
            <LogOut className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </nav>
  );
}
