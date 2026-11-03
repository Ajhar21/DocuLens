import { FileText, Files, type LucideIcon } from "lucide-react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  to: string;
  icon: LucideIcon;
}

// Structured for future Day 2+ routes while rendering only routes that exist today.
const NAV_ITEMS: readonly NavItem[] = [
  {
    label: "Documents",
    to: "/documents",
    icon: Files,
  },
];

interface SidebarProps {
  onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
  return (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-foreground">
      <div className="flex h-14 items-center gap-2.5 border-b px-5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <FileText className="h-4 w-4" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-none tracking-tight text-foreground">
            DocuLens
          </span>
          <span className="text-[11px] text-muted-foreground">
            Document Intelligence
          </span>
        </div>
      </div>

      <nav
        aria-label="Primary navigation"
        className="flex-1 space-y-1 px-3 py-4"
      >
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-sidebar-foreground hover:bg-accent hover:text-accent-foreground",
                )
              }
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="border-t p-4">
        <p className="text-xs text-muted-foreground">
          Day 1 Ingestion &amp; Queue Workspace
        </p>
      </div>
    </div>
  );
}

