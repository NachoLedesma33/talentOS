"use client";

import { useCallback, useEffect, useState } from "react";
import { MembersPanel } from "../../components/MembersPanel";
import { WorkspaceShell } from "../../components/WorkspaceShell";
import { OrganizationSelector } from "../../components/OrganizationSelector";
import { ApiError, apiFetch } from "../../lib/api";
import type { MeResponse } from "../../lib/types";
import { Button } from "../../components/ui/shadcn/button";
import { Card } from "../../components/ui/shadcn/card";

type SessionStatus =
  | "loading"
  | "ready"
  | "unauthorized"
  | "forbidden"
  | "notFound"
  | "serverError"
  | "error";

function requestSession(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/v1/auth/me");
}

export default function DashboardPage() {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<MeResponse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [activeOrganizationId, setActiveOrganizationId] = useState<string | null>(null);

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
          onClick={() => {
            setStatus("loading");
            setMessage(null);
            requestSession().then(applySessionSuccess, applySessionError);
          }}
        >
          Reintentar
        </Button>
      </section>
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
