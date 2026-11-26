"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { MembersPanel } from "../../components/MembersPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";
import { OrganizationSelector } from "../../components/OrganizationSelector";
import { ApiError, apiFetch } from "../../lib/api";
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

function requestSession(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/v1/auth/me");
}

export default function DashboardPage() {
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
      <p role="status" aria-live="polite" className="text-sm text-text-muted">
        Cargando sesión…
      </p>
    );
  }

  if (status === "unauthorized") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Sesión requerida</h1>
        <p className="text-sm text-text-muted">
          {message ?? "Inicia sesión para continuar."}
        </p>
        <p className="text-sm">
          <a href="/login">Ir a iniciar sesión</a>
        </p>
      </section>
    );
  }

  if (status === "forbidden") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Permisos insuficientes</h1>
        <p className="text-sm text-text-muted">
          {message ?? "Tu cuenta no puede acceder a esta sección."}
        </p>
      </section>
    );
  }

  if (status === "notFound") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">No encontrado.</h1>
        <p className="text-sm text-text-muted">{message}</p>
      </section>
    );
  }

  if (status === "serverError") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">Error del servidor.</h1>
        <p className="text-sm text-text-muted">{message}</p>
      </section>
    );
  }

  if (status === "error") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          No se pudo cargar el panel
        </h1>
        <p className="text-sm text-text-muted">{message}</p>
        <Button
          type="button"
          variant="outline"
          onClick={reloadSession}
        >
          Reintentar
        </Button>
      </section>
    );
  }

  const onboardingStep = status === "ready" ? user?.onboarding?.step ?? "complete" : "complete";
  const hasOrganization = (user?.organizations?.length ?? 0) > 0;

  if (onboardingStep === "create_organization") {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 py-10">
        <Card className="w-full max-w-md space-y-4 p-5">
          <div className="space-y-1">
            <h1 className="text-2xl font-semibold tracking-tight">Creá tu organización</h1>
            <p className="text-sm text-text-muted">
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
      </main>
    );
  }

  if (onboardingStep === "accept_invitation") {
    return (
      <main className="flex min-h-screen items-center justify-center px-4 py-10">
        <Card className="w-full max-w-md space-y-4 p-5">
          <h1 className="text-2xl font-semibold tracking-tight">Invitación pendiente</h1>
          <p className="text-sm text-text-muted">
            Tenés una invitación pendiente. Abrí el enlace que recibiste por correo para
            aceptarla.
          </p>
          <Button type="button" variant="outline" onClick={reloadSession}>
            Ya la acepté, revisar de nuevo
          </Button>
        </Card>
      </main>
    );
  }

  return (
    <WorkspaceShell>
      <div className="space-y-6">
        <Card className="space-y-1 p-4">
          <h1 className="text-2xl font-semibold tracking-tight">Panel</h1>
          <p className="text-sm text-text-muted">
            Sesión activa: {user?.name} ({user?.email})
          </p>
        </Card>

        <Card className="space-y-2 p-4">
          <h2 id="first-steps-heading" className="text-sm font-semibold text-text-muted">
            Primeros pasos
          </h2>
          <ol aria-labelledby="first-steps-heading" className="space-y-2 text-sm">
            <li className="flex items-center gap-2">
              <span aria-hidden="true">{hasOrganization ? "✓" : "○"}</span>
              <span>
                Crear tu organización
                {hasOrganization ? (
                  <span className="ml-2 text-text-muted">(completado)</span>
                ) : null}
              </span>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true">○</span>
              <a href="#members-heading">Invitar a tu equipo</a>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true">○</span>
              <a href="/jobs">Publicar una vacante</a>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden="true">○</span>
              <a href="/candidates">Añadir candidatos</a>
            </li>
          </ol>
        </Card>

        <Card className="p-4">
          <OrganizationSelector onActiveOrganizationChange={setActiveOrganizationId} />
        </Card>
        <Card className="p-4">
          <MembersPanel organizationId={activeOrganizationId} />
        </Card>

        <Card className="space-y-2 p-4">
          <h2 id="recruitment-heading" className="text-sm font-semibold text-text-muted">
            Recruitment Core
          </h2>
          <nav aria-labelledby="recruitment-heading">
            <ul className="flex flex-wrap gap-2">
              <li><Button asChild variant="outline" size="sm"><a href="/jobs">Vacantes</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/candidates">Candidatos</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/applications">Pipeline</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/documents">Documentos</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/assessment">Evaluación</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/agents">Agentes</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/automations">Automatizaciones</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/integrations">Integraciones</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/interviews">Entrevistas</a></Button></li>
              <li><Button asChild variant="outline" size="sm"><a href="/analytics">Analítica</a></Button></li>
            </ul>
          </nav>
        </Card>
      </div>
    </WorkspaceShell>
  );
}
