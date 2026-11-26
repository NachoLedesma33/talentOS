"use client";

import Link from "next/link";
import { useState, type ChangeEvent, type ReactNode } from "react";
import { ACTIVE_ORG_STORAGE_KEY, ApiError, apiFetch } from "../lib/api";
import type { MeResponse, Organization } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Select } from "./ui/shadcn/select";
import { CommandMenu } from "./CommandMenu";

type LoadStatus = "idle" | "loading" | "ready" | "error";

function describeError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

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
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [user, setUser] = useState<MeResponse | null>(null);
  const [sessionStatus, setSessionStatus] = useState<LoadStatus>("idle");
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeOrgId, setActiveOrgId] = useState("");
  const [orgStatus, setOrgStatus] = useState<LoadStatus>("idle");
  const [notice, setNotice] = useState<string | null>(null);
  const [headerError, setHeaderError] = useState<string | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  function loadSession(force = false) {
    if (!force && sessionStatus !== "idle") {
      return;
    }
    setHeaderError(null);
    setSessionStatus("loading");
    apiFetch<MeResponse>("/api/v1/auth/me").then(
      (me) => {
        setUser(me);
        setSessionStatus("ready");
      },
      (cause: unknown) => {
        setSessionStatus("error");
        setHeaderError(describeError(cause, "No se pudo cargar la sesión."));
      },
    );
  }

  function loadOrganizations(force = false) {
    if (!force && orgStatus !== "idle") {
      return;
    }
    setHeaderError(null);
    setOrgStatus("loading");
    apiFetch<Organization[]>("/api/v1/organizations").then(
      (items) => {
        if (!Array.isArray(items)) {
          setOrganizations([]);
          setOrgStatus("ready");
          return;
        }
        const storedId = window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
        const nextId = items.some((item) => item.id === storedId)
          ? (storedId ?? "")
          : (items[0]?.id ?? "");
        if (nextId && nextId !== storedId) {
          window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, nextId);
        }
        setOrganizations(items);
        setActiveOrgId(nextId);
        setOrgStatus("ready");
      },
      (cause: unknown) => {
        setOrgStatus("error");
        setHeaderError(describeError(cause, "No se pudieron cargar las organizaciones."));
      },
    );
  }

  function handleOrgChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextId = event.target.value;
    setActiveOrgId(nextId);
    if (nextId) {
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, nextId);
    }
  }

  async function handleLogout() {
    setLoggingOut(true);
    setNotice(null);
    setHeaderError(null);
    try {
      await apiFetch<{ message: string }>("/api/v1/auth/logout", { method: "POST" });
      setUser(null);
      setNotice("Sesión cerrada.");
    } catch (cause) {
      setHeaderError(describeError(cause, "No se pudo cerrar la sesión."));
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <header className="sticky top-0 z-20 border-b border-border-subtle bg-surface">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 sm:px-6">
          <a
            href="/dashboard"
            className="flex items-center gap-3 rounded-md text-text"
          >
            <span
              aria-hidden="true"
              className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-on-accent"
            >
              <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4">
                <path
                  d="M5 6h14M12 6v12M8 18h8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                />
              </svg>
            </span>
            <span className="text-sm font-semibold tracking-tight">TalentOS</span>
            <span className="hidden text-[11px] uppercase tracking-widest text-text-muted sm:inline">
              Workspace
            </span>
          </a>

          <nav aria-label="Ruta de navegación" className="order-3 w-full md:order-none md:w-auto md:flex-1">
            <ol className="flex gap-2 text-xs text-text-muted">
              <li>
                <a href="/dashboard">Inicio</a>
              </li>
              <li aria-current="page" className="font-medium text-text">
                {section}
              </li>
            </ol>
          </nav>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2">
              {orgStatus === "idle" ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label="Organización activa en la barra"
                  onClick={() => loadOrganizations()}
                >
                  Organización activa
                </Button>
              ) : null}
              {orgStatus === "loading" ? (
                <p role="status" className="text-xs text-text-muted">
                  Cargando organización…
                </p>
              ) : null}
              {orgStatus === "error" ? (
                <>
                  <p role="alert" className="text-xs text-text">
                    Error: organización no disponible.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => loadOrganizations(true)}
                  >
                    Reintentar organizaciones
                  </Button>
                </>
              ) : null}
              {orgStatus === "ready" && organizations.length === 0 ? (
                <p className="text-xs text-text-muted">Sin organizaciones.</p>
              ) : null}
              {orgStatus === "ready" && organizations.length > 0 ? (
                <>
                  <label htmlFor="workspace-active-org" className="sr-only">
                    Organización activa en la barra
                  </label>
                  <Select
                    id="workspace-active-org"
                    aria-label="Organización activa en la barra"
                    className="h-8 w-40 text-xs"
                    value={activeOrgId}
                    onChange={handleOrgChange}
                  >
                    {organizations.map((organization) => (
                      <option key={organization.id} value={organization.id}>
                        {organization.name}
                      </option>
                    ))}
                  </Select>
                </>
              ) : null}
            </div>
            <CommandMenu />
            <div className="relative">
              <Button
                type="button"
                variant="outline"
                size="sm"
                aria-expanded={userMenuOpen}
                aria-controls="workspace-user-menu"
                onClick={() => {
                  if (!userMenuOpen) {
                    loadSession();
                  }
                  setUserMenuOpen((open) => !open);
                }}
              >
                {user ? user.name : sessionStatus === "loading" ? "Cargando usuario…" : "Cuenta"}
              </Button>
              {userMenuOpen ? (
                <div
                  id="workspace-user-menu"
                  className="absolute right-0 z-10 mt-2 w-64 space-y-2 rounded-md border border-border-subtle bg-surface p-3 text-sm shadow-md"
                >
                  {sessionStatus === "loading" ? (
                    <p role="status" className="text-text-muted">
                      Cargando sesión…
                    </p>
                  ) : null}
                  {user ? (
                    <>
                      <p className="font-semibold">{user.name}</p>
                      <p className="text-text-muted">{user.email}</p>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={loggingOut}
                        onClick={() => void handleLogout()}
                      >
                        {loggingOut ? "Cerrando sesión…" : "Cerrar sesión"}
                      </Button>
                    </>
                  ) : null}
                  {sessionStatus === "error" || (sessionStatus === "ready" && !user) ? (
                    <a href="/login" className="block font-medium text-accent">
                      Iniciar sesión
                    </a>
                  ) : null}
                  {notice ? (
                    <p role="status" aria-live="polite" className="text-text-muted">
                      {notice}
                    </p>
                  ) : null}
                  {headerError ? (
                    <p role="alert" className="text-text">
                      Error: {headerError}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-4 py-8 sm:px-6 md:flex-row">
        <aside
          aria-label="Navegación del workspace"
          className="hidden w-52 shrink-0 md:block"
        >
          <div className="sticky top-24 space-y-4">
            <p className="px-2 text-[11px] font-semibold uppercase tracking-widest text-text-muted">
              Espacio de trabajo
            </p>
            <nav aria-label="Secciones del workspace">
              <ul className="space-y-1 text-sm">
                {workspaceLinks.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className="block rounded-md px-2 py-2 text-text-muted transition-colors hover:bg-surface-muted hover:text-text"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          </div>
        </aside>

        <div className="min-w-0 flex-1 space-y-6">
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-expanded={mobileNavOpen}
            aria-controls="workspace-mobile-nav"
            onClick={() => setMobileNavOpen((open) => !open)}
            className="md:hidden"
          >
            {mobileNavOpen ? "Ocultar menú" : "Mostrar menú"}
          </Button>
          <nav
            id="workspace-mobile-nav"
            aria-label="Navegación móvil del workspace"
            className={`${mobileNavOpen ? "block" : "hidden"} md:hidden`}
          >
            <ul className="flex flex-wrap gap-3 rounded-lg bg-surface-muted p-3 text-sm">
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

      <footer className="border-t border-border-subtle bg-surface-muted">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-xs text-text-muted sm:px-6">
          <p>TalentOS · reclutamiento asistido, trazable y supervisado.</p>
          <nav aria-label="Enlaces del workspace" className="flex flex-wrap gap-4">
            <Link href="/">Portada</Link>
            <a href="http://localhost:8000/health">/health</a>
            <a href="http://localhost:8000/ready">/ready</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
