import { KeyRound, LogOut, Menu } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ROLE_LABELS } from "@/features/auth/roles";
import { useAuth } from "@/features/auth/use-auth";
import { getInitials } from "@/lib/format";

interface TopBarProps {
  onOpenMobileMenu: () => void;
}

export function TopBar({ onOpenMobileMenu }: TopBarProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;

  const roleLabel = ROLE_LABELS[user.role];

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/95 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="lg:hidden"
          onClick={onOpenMobileMenu}
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </Button>
        <span className="text-sm font-medium text-muted-foreground">
          Workspace
        </span>
      </div>

      <div className="flex items-center gap-3">
        <Badge
          variant="secondary"
          className="capitalize"
          data-testid="user-role-badge"
        >
          {roleLabel}
        </Badge>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              className="flex h-9 items-center gap-2.5 rounded-full pl-1.5 pr-3"
              aria-label={`Account menu for ${user.full_name}`}
            >
              <Avatar className="h-7 w-7">
                <AvatarFallback>{getInitials(user.full_name)}</AvatarFallback>
              </Avatar>
              <span className="hidden max-w-[160px] truncate text-sm font-medium sm:inline">
                {user.full_name}
              </span>
            </Button>
          </DropdownMenuTrigger>

          <DropdownMenuContent align="end" className="w-60">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <p className="truncate text-sm font-semibold text-foreground">
                    {user.full_name}
                  </p>
                  <Badge variant="outline" className="text-[11px] capitalize">
                    {roleLabel}
                  </Badge>
                </div>
                <p className="truncate text-xs text-muted-foreground">
                  {user.email}
                </p>
              </div>
            </DropdownMenuLabel>

            <DropdownMenuSeparator />

            <DropdownMenuItem onClick={() => navigate("/change-password")}>
              <KeyRound className="h-4 w-4" />
              <span>Change password</span>
            </DropdownMenuItem>

            <DropdownMenuItem
              onClick={() => logout("manual")}
              className="text-destructive focus:bg-destructive/10 focus:text-destructive"
              data-testid="logout-menu-item"
            >
              <LogOut className="h-4 w-4" />
              <span>Sign out</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

