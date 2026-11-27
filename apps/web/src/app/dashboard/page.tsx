"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { MembersPanel } from "../../components/MembersPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";
import { OrganizationSelector } from "../../components/OrganizationSelector";
import { ApiError, apiFetch } from "../../lib/api";
import { useI18n } from "../../lib/i18n";
import type { MeResponse, Organization } from "../../lib/types";
import { Button } from "../../components/ui/shadcn/button";
import { Card } from "../../components/ui/shadcn/card";
import { Input } from "../../components/ui/shadcn/input";
import { Label } from "../../components/ui/shadcn/label";

type SessionStatus =
  | "loading"
  | "ready"
  | "unauthorized"
  | "forbidden"
  | "notFound"
  | "serverError"
  | "error";

type SubmitStatus = "idle" | "loading" | "error";
type OrganizationPayload = Pick<Organization, "name" | "slug">;

const moduleLinks = [
  { href: "/jobs", label: "Vacantes", detail: "Requisitos y etapas" },
  { href: "/candidates", label: "Candidatos", detail: "Perfiles y evidencia" },
  { href: "/applications", label: "Pipeline", detail: "Postulaciones por etapa" },
  { href: "/documents", label: "Documentos", detail: "Archivos privados" },
  { href: "/assessment", label: "Evaluación", detail: "Criterios y brechas" },
  { href: "/agents", label: "Agentes", detail: "Ejecuciones y traza" },
  { href: "/automations", label: "Automatizaciones", detail: "Reglas y aprobaciones" },
  { href: "/integrations", label: "Integraciones", detail: "Adaptadores y entregas" },
  { href: "/interviews", label: "Entrevistas", detail: "Agenda y guiones" },
  { href: "/analytics", label: "Analítica", detail: "Métricas del proceso" },
] as const;

function requestSession(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/v1/auth/me");
}

export default function DashboardPage() {
  const { t } = useI18n();
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(null);
  const [orgStatus, setOrgStatus] = useState<SubmitStatus>("idle");
  const [orgMessage, setOrgMessage] = useState<string | null>(null);

  const applySessionSuccess = useCallback((currentUser: MeResponse) => {
    setUser(currentUser);
    setStatus("ready");
  }, []);

  const applySessionError = useCallback((error: unknown) => {
    setUser(null);
    setActiveOrganizationId(null);
    if (error instanceof ApiError && error.status === 401) {
      setStatus("unauthorized");
      setMessage(error.message);
    } else if (error instanceof ApiError && error.status === 403) {
      setStatus("forbidden");
      setMessage(error.message);
    } else if (error instanceof ApiError && error.status === 404) {
      setStatus("notFound");
      setMessage(error.message);
    } else if (error instanceof ApiError && error.status === 500) {
      setStatus("serverError");
      setMessage(error.message);
    } else {
      setStatus("error");
      setMessage(error instanceof ApiError ? error.message : "No se pudo cargar la sesión.");
    }
  }, []);

  useEffect(() => {
    let active = true;
    requestSession().then(
      (currentUser) => {
        if (active) {
          applySessionSuccess(currentUser);
        }
      },
      (error: unknown) => {
        if (active) {
          applySessionError(error);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [applySessionSuccess, applySessionError]);

  const reloadSession = useCallback(() => {
    setStatus("loading");
    setMessage(null);
    requestSession().then(applySessionSuccess, applySessionError);
  }, [applySessionSuccess, applySessionError]);

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload: OrganizationPayload = {
      name: String(data.get("name") ?? "").trim(),
      slug: String(data.get("slug") ?? "").trim(),
    };
    setOrgStatus("loading");
    setOrgMessage(null);
    try {
      await apiFetch<Organization>("/api/v1/organizations", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      reloadSession();
    } catch (error) {
      setOrgStatus("error");
      setOrgMessage(
        error instanceof ApiError ? error.message : "No se pudo crear la organización.",
      );
    }
  }

  if (status === "loading") {
    return (
      <section role="status" aria-live="polite" className="mx-auto max-w-3xl py-16">
        <p className="text-sm text-text-muted">Cargando sesión…</p>
      </section>
    );
  }

  if (status === "unauthorized") {
    return (
      <section role="alert" className="mx-auto max-w-xl space-y-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">Sesión requerida</h1>
        <p className="text-sm leading-relaxed text-text-muted">
          {message ?? "Inicia sesión para continuar."}
        </p>
        <Button asChild>
          <Link href="/login">Ir a iniciar sesión</Link>
        </Button>
      </section>
    );
  }

  if (status === "forbidden") {
    return (
      <section role="alert" className="mx-auto max-w-xl space-y-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">Permisos insuficientes</h1>
        <p className="text-sm leading-relaxed text-text-muted">
          {message ?? "Tu cuenta no puede acceder a esta sección."}
        </p>
      </section>
    );
  }

  if (status === "notFound") {
    return (
      <section role="alert" className="mx-auto max-w-xl space-y-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">No encontrado.</h1>
        <p className="text-sm leading-relaxed text-text-muted">{message}</p>
      </section>
    );
  }

  if (status === "serverError") {
    return (
      <section role="alert" className="mx-auto max-w-xl space-y-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">Error del servidor.</h1>
        <p className="text-sm leading-relaxed text-text-muted">{message}</p>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section role="alert" className="mx-auto max-w-xl space-y-4 py-16">
        <h1 className="text-3xl font-semibold tracking-tight">No se pudo cargar el panel</h1>
        <p className="text-sm leading-relaxed text-text-muted">{message}</p>
        <Button type="button" variant="outline" onClick={reloadSession}>
          Reintentar
        </Button>
      </section>
    );
  }

  const onboardingStep = status === "ready" ? user?.onboarding?.step ?? "complete" : "complete";
  const hasOrganization = (user?.organizations?.length ?? 0) > 0;

  if (onboardingStep === "create_organization") {
    return (
      <section className="flex min-h-[70vh] items-center justify-center px-4 py-10">
        <Card className="w-full max-w-lg space-y-5 p-6">
          <div className="space-y-2">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
              Primer paso
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">Creá tu organización</h1>
            <p className="text-sm leading-relaxed text-text-muted">
              Primer paso para usar TalentOS. Después podés invitar a tu equipo.
            </p>
          </div>
          <form
            onSubmit={handleCreateOrganization}
            aria-busy={orgStatus === "loading"}
            className="space-y-4"
          >
            <div className="space-y-1">
              <Label htmlFor="org-name" className="block">
                Nombre
              </Label>
              <Input id="org-name" name="name" type="text" required maxLength={200} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="org-slug" className="block">
                Identificador
              </Label>
              <Input
                id="org-slug"
                name="slug"
                type="text"
                required
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
              />
            </div>
            <Button type="submit" disabled={orgStatus === "loading"}>
              {orgStatus === "loading" ? "Creando…" : "Crear organización"}
            </Button>
            <p
              aria-live="assertive"
              role={orgStatus === "error" ? "alert" : undefined}
              className="min-h-5 text-sm text-text-muted"
            >
              {orgStatus === "error" ? `Error: ${orgMessage}` : null}
            </p>
          </form>
        </Card>
      </section>
    );
  }

  if (onboardingStep === "accept_invitation") {
    return (
      <section className="flex min-h-[70vh] items-center justify-center px-4 py-10">
        <Card className="w-full max-w-lg space-y-5 p-6">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
            Invitación
          </p>
          <h1 className="text-3xl font-semibold tracking-tight">Invitación pendiente</h1>
          <p className="text-sm leading-relaxed text-text-muted">
            Tenés una invitación pendiente. Abrí el enlace que recibiste por correo para
            aceptarla.
          </p>
          <Button type="button" variant="outline" onClick={reloadSession}>
            Ya la acepté, revisar de nuevo
          </Button>
        </Card>
      </section>
    );
  }

  return (
    <WorkspaceShell>
      <div className="space-y-8">
        <section className="rounded-2xl bg-surface-muted p-6 sm:p-8">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="max-w-2xl space-y-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-accent">
                Resumen del workspace
              </p>
              <h1 className="text-3xl font-semibold tracking-tight text-text sm:text-4xl">Panel</h1>
              <p className="text-sm text-text-muted">
                Sesión activa: {user?.name} ({user?.email})
              </p>
              <p className="text-base leading-relaxed text-text-muted">
                Prepará vacantes, contrastá evidencia y dejá cada decisión con su rastro. El
                workspace muestra el estado real; nada se decide por inferencia.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button asChild size="lg">
                <Link href="/jobs">Nueva vacante</Link>
              </Button>
              <Button asChild variant="outline" size="lg">
                <Link href="/candidates">Ver candidatos</Link>
              </Button>
            </div>
          </div>
        </section>

        <section aria-label="Indicadores del workspace" className="grid gap-4 sm:grid-cols-3">
          <Card className="space-y-2 p-5">
            <p className="text-xs uppercase tracking-wider text-text-muted">Organizaciones</p>
            <p className="text-3xl font-semibold tracking-tight text-text">
              {user?.organizations?.length ?? 0}
            </p>
            <p className="text-xs text-text-muted">Disponibles para esta sesión.</p>
          </Card>
          <Card className="space-y-2 p-5">
            <p className="text-xs uppercase tracking-wider text-text-muted">Paso actual</p>
            <p className="truncate text-lg font-semibold text-text">{onboardingStep}</p>
            <p className="text-xs text-text-muted">Estado informado por la API.</p>
          </Card>
          <Card className="space-y-2 p-5">
            <p className="text-xs uppercase tracking-wider text-text-muted">
              Acciones externas automáticas
            </p>
            <p className="text-3xl font-semibold tracking-tight text-text">0</p>
            <p className="text-xs text-text-muted">Toda salida sensible espera aprobación.</p>
          </Card>
        </section>

        <Card className="space-y-4 p-5">
          <div className="space-y-1">
            <h2 id="first-steps-heading" className="text-lg font-semibold tracking-tight text-text">
              Primeros pasos
            </h2>
            <p className="text-sm text-text-muted">
              Cuatro acciones para dejar el workspace listo para contratar.
            </p>
          </div>
          <ol aria-labelledby="first-steps-heading" className="grid gap-3 sm:grid-cols-2">
            <li className="flex items-start gap-3 rounded-xl bg-surface-muted px-4 py-3 text-sm">
              <span aria-hidden="true">{hasOrganization ? "✓" : "○"}</span>
              <span>
                Crear tu organización
                {hasOrganization ? (
                  <span className="ml-2 text-text-muted">(completado)</span>
                ) : null}
              </span>
            </li>
            <li className="flex items-start gap-3 rounded-xl bg-surface-muted px-4 py-3 text-sm">
              <span aria-hidden="true">○</span>
              <Link href="#members-heading">Invitar a tu equipo</Link>
            </li>
            <li className="flex items-start gap-3 rounded-xl bg-surface-muted px-4 py-3 text-sm">
              <span aria-hidden="true">○</span>
              <Link href="/jobs">Publicar una vacante</Link>
            </li>
            <li className="flex items-start gap-3 rounded-xl bg-surface-muted px-4 py-3 text-sm">
              <span aria-hidden="true">○</span>
              <Link href="/candidates">Añadir candidatos</Link>
            </li>
          </ol>
        </Card>

        <Card className="p-5">
          <OrganizationSelector onActiveOrganizationChange={setActiveOrganizationId} />
        </Card>
        <Card className="p-5">
          <MembersPanel organizationId={activeOrganizationId} />
        </Card>

        <Card className="space-y-4 p-5">
          <div className="space-y-1">
            <h2 id="recruitment-heading" className="text-lg font-semibold tracking-tight text-text">
              {t("shell.recruitment")}
            </h2>
            <p className="text-sm text-text-muted">
              Módulos del recorrido. Cada uno responde una decisión concreta.
            </p>
          </div>
          <nav aria-labelledby="recruitment-heading">
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {moduleLinks.map((module) => (
                <li key={module.href}>
                  <Button asChild variant="outline" className="h-full w-full justify-start rounded-xl p-4">
                    <Link
                      href={module.href}
                      aria-label={module.label}
                      className="group flex flex-col items-start gap-1 py-1"
                    >
                      <span className="text-sm font-semibold">{module.label}</span>
                      <span className="text-xs font-normal text-text-muted group-hover:text-text">{module.detail}</span>
                    </Link>
                  </Button>
                </li>
              ))}
            </ul>
          </nav>
        </Card>
      </div>
    </WorkspaceShell>
  );
}
