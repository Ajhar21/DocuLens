import { useState } from "react";
import { Outlet } from "react-router-dom";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[240px_1fr]">
      {/* Desktop persistent sidebar */}
      <aside className="hidden border-r lg:block">
        <div className="sticky top-0 h-screen">
          <Sidebar />
        </div>
      </aside>

      {/* Mobile collapsible sheet sidebar */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent className="p-0">
          <SheetTitle className="sr-only">Navigation menu</SheetTitle>
          <SheetDescription className="sr-only">
            Navigate between DocuLens workspace sections
          </SheetDescription>
          <Sidebar onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenMobileMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-6 sm:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

