"use client";

import Link from "next/link";
import { useState, type ChangeEvent, type ReactNode } from "react";
import { ACTIVE_ORG_STORAGE_KEY, ApiError, apiFetch } from "../lib/api";
import { LocaleToggle, useI18n, type MessageKey } from "../lib/i18n";
import type { MeResponse, Organization } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Select } from "./ui/shadcn/select";
import { CommandMenu } from "./CommandMenu";
import { AssistantPanel, type AssistantSurface } from "./AssistantPanel";

type LoadStatus = "idle" | "loading" | "ready" | "error";

function describeError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const workspaceLinks: ReadonlyArray<{ href: string; labelKey: MessageKey }> = [
  { href: "/dashboard", labelKey: "shell.panel" },
  { href: "/dashboard#organization-selector-heading", labelKey: "shell.organization" },
  { href: "/dashboard#members-heading", labelKey: "shell.members" },
  { href: "/dashboard#recruitment-heading", labelKey: "shell.recruitment" },
];

const sectionKeys: Readonly<Record<string, MessageKey>> = {
  Panel: "shell.panel",
  Analítica: "shell.analytics",
  Evaluación: "shell.assessment",
  Agentes: "shell.agents",
  Pipeline: "shell.pipeline",
  Candidatos: "shell.candidates",
  Automatizaciones: "shell.automations",
  Documentos: "shell.documents",
  Integraciones: "shell.integrations",
  Entrevistas: "shell.interviews",
  Vacantes: "shell.jobs",
};

const sectionSurfaces: Readonly<Record<string, AssistantSurface>> = {
  Panel: "dashboard",
  Analítica: "analytics",
  Evaluación: "assessment",
  Agentes: "agents",
  Pipeline: "applications",
  Candidatos: "candidates",
  Automatizaciones: "automations",
  Documentos: "documents",
  Integraciones: "integrations",
  Entrevistas: "interviews",
  Vacantes: "jobs",
};

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
  const { t } = useI18n();
  const sectionLabel = sectionKeys[section] ? t(sectionKeys[section]) : section;
  const assistantSurface = sectionSurfaces[section];

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
        setHeaderError(describeError(cause, t("shell.sessionError")));
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
        setHeaderError(describeError(cause, t("shell.orgsError")));
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
      setNotice(t("shell.logoutNotice"));
      window.localStorage.removeItem(ACTIVE_ORG_STORAGE_KEY);
      window.setTimeout(() => window.location.replace("/"), 600);
    } catch (cause) {
      setHeaderError(describeError(cause, t("shell.logoutError")));
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
              {t("shell.workspace")}
            </span>
          </a>

          <nav aria-label={t("shell.breadcrumb")} className="order-3 w-full md:order-none md:w-auto md:flex-1">
            <ol className="flex gap-2 text-xs text-text-muted">
              <li>
                <a href="/dashboard" className="text-sm">{t("shell.home")}</a>
              </li>
              <li aria-current="page" className="font-medium text-text">
                {sectionLabel}
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
                  aria-label={t("shell.activeOrgAria")}
                  onClick={() => loadOrganizations()}
                >
                  {t("shell.activeOrg")}
                </Button>
              ) : null}
              {orgStatus === "loading" ? (
                <p role="status" className="text-xs text-text-muted">
                  {t("shell.loadingOrg")}
                </p>
              ) : null}
              {orgStatus === "error" ? (
                <>
                  <p role="alert" className="text-xs text-text">
                    {t("shell.orgError")}
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => loadOrganizations(true)}
                  >
                    {t("shell.retryOrgs")}
                  </Button>
                </>
              ) : null}
              {orgStatus === "ready" && organizations.length === 0 ? (
                <p className="text-xs text-text-muted">{t("shell.noOrgs")}</p>
              ) : null}
              {orgStatus === "ready" && organizations.length > 0 ? (
                <>
                  <label htmlFor="workspace-active-org" className="sr-only">
                    {t("shell.activeOrgAria")}
                  </label>
                  <Select
                    id="workspace-active-org"
                    aria-label={t("shell.activeOrgAria")}
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
            <LocaleToggle />
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
                {user ? user.name : sessionStatus === "loading" ? t("shell.loadingUser") : t("shell.account")}
              </Button>
              {userMenuOpen ? (
                <div
                  id="workspace-user-menu"
                  className="absolute right-0 z-10 mt-2 w-64 space-y-2 rounded-md border border-border-subtle bg-surface p-3 text-sm shadow-md"
                >
                  {sessionStatus === "loading" ? (
                    <p role="status" className="text-text-muted">
                      {t("shell.loadingSession")}
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
                        {loggingOut ? t("shell.closingSession") : t("shell.logout")}
                      </Button>
                    </>
                  ) : null}
                  {sessionStatus === "error" || (sessionStatus === "ready" && !user) ? (
                    <a href="/login" className="block font-medium text-accent">
                      {t("shell.login")}
                    </a>
                  ) : null}
                  {notice ? (
                    <p role="status" aria-live="polite" className="text-text-muted">
                      {notice}
                    </p>
                  ) : null}
                  {headerError ? (
                    <p role="alert" className="text-text">
                      {t("shell.errorPrefix")}
                      {headerError}
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
          aria-label={t("shell.navWorkspace")}
          className="hidden w-52 shrink-0 md:block"
        >
          <div className="sticky top-24 space-y-4">
            <p className="px-2 text-[11px] font-semibold uppercase tracking-widest text-text-muted">
              {t("shell.workspaceSpace")}
            </p>
            <nav aria-label={t("shell.navSections")}>
              <ul className="space-y-1 text-sm">
                {workspaceLinks.map((link) => (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className="block rounded-md px-2 py-2 text-text-muted transition-colors hover:bg-surface-muted hover:text-text"
                    >
                      {t(link.labelKey)}
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
            {mobileNavOpen ? t("shell.hideMenu") : t("shell.showMenu")}
          </Button>
          <nav
            id="workspace-mobile-nav"
            aria-label={t("shell.navMobile")}
            className={`${mobileNavOpen ? "block" : "hidden"} md:hidden`}
          >
            <ul className="flex flex-wrap gap-3 rounded-lg bg-surface-muted p-3 text-sm">
              {workspaceLinks.map((link) => (
                <li key={link.href}>
                  <a href={link.href}>{t(link.labelKey)}</a>
                </li>
              ))}
            </ul>
          </nav>

          {children}
          {assistantSurface !== undefined && <AssistantPanel surface={assistantSurface} />}
        </div>
      </div>

      <footer className="border-t border-border-subtle bg-surface-muted">
        <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-text-muted sm:px-6">
          <p>{t("shell.footerTagline")}</p>
          <nav aria-label={t("shell.footerLinks")} className="flex flex-wrap gap-4">
            <Link href="/">{t("shell.homeLink")}</Link>
            <a href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/privacy-policy.md">
              {t("shell.privacy")}
            </a>
            <a href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/terms-of-service.md">
              {t("shell.terms")}
            </a>
            <a href="http://localhost:8000/health">/health</a>
            <a href="http://localhost:8000/ready">/ready</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
