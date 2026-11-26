"use client";

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
        <header className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle pb-3">
          <p className="text-sm font-semibold tracking-tight">Workspace</p>
          <div className="flex flex-wrap items-center gap-3">
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
            <nav aria-label="Ruta de navegación">
              <ol className="flex gap-2 text-xs text-text-muted">
                <li>
                  <a href="/dashboard">Inicio</a>
                </li>
                <li aria-current="page">{section}</li>
              </ol>
            </nav>
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
                  className="absolute right-0 z-10 mt-2 w-64 space-y-2 rounded-md border border-border-subtle bg-background p-3 text-sm shadow-md"
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
                    <a href="/login" className="block underline">
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
