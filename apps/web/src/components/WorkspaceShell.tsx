"use client";

import { useState, type ReactNode } from "react";
import { Button } from "./ui/shadcn/button";

const workspaceLinks = [
  { href: "/dashboard", label: "Panel" },
  { href: "/dashboard#organization-selector-heading", label: "Organización" },
  { href: "/dashboard#members-heading", label: "Miembros" },
  { href: "/dashboard#recruitment-heading", label: "Recruitment Core" },
];

export function WorkspaceShell({
  children,
  section = "Panel",
}: Readonly<{ children: ReactNode; section?: string }>) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  return (
    <div className="flex flex-col gap-6 md:flex-row">
      <aside
        aria-label="Navegación del workspace"
        className="hidden w-48 shrink-0 border-r border-border-subtle pr-4 md:block"
      >
        <nav aria-label="Secciones del workspace">
          <ul className="space-y-2 text-sm">
            {workspaceLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href}>{link.label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="mb-4 flex items-center justify-between gap-4 border-b border-border-subtle pb-3">
          <p className="text-sm font-semibold tracking-tight">Workspace</p>
          <nav aria-label="Ruta de navegación">
            <ol className="flex gap-2 text-xs text-text-muted">
              <li>
                <a href="/dashboard">Inicio</a>
              </li>
              <li aria-current="page">{section}</li>
            </ol>
          </nav>
        </header>

        <Button
          type="button"
          variant="outline"
          size="sm"
          aria-expanded={mobileNavOpen}
          aria-controls="workspace-mobile-nav"
          onClick={() => setMobileNavOpen((open) => !open)}
          className="mb-4 md:hidden"
        >
          {mobileNavOpen ? "Ocultar menú" : "Mostrar menú"}
        </Button>
        <nav
          id="workspace-mobile-nav"
          aria-label="Navegación móvil del workspace"
          className={`${mobileNavOpen ? "block" : "hidden"} mb-4 md:hidden`}
        >
          <ul className="flex flex-wrap gap-3 text-sm">
            {workspaceLinks.map((link) => (
              <li key={link.href}>
                <a href={link.href}>{link.label}</a>
              </li>
            ))}
          </ul>
        </nav>

        {children}
      </div>
    </div>
  );
}
