"use client";

import { useCallback, useEffect, useState } from "react";
import { MembersPanel } from "../../components/MembersPanel";
import { OrganizationSelector } from "../../components/OrganizationSelector";
import { ApiError, apiFetch } from "../../lib/api";
import type { MeResponse } from "../../lib/types";

type SessionStatus = "loading" | "ready" | "unauthorized" | "forbidden" | "error";

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

  if (status === "error") {
    return (
      <section role="alert" className="space-y-3">
        <h1 className="text-2xl font-semibold tracking-tight">
          No se pudo cargar el panel
        </h1>
        <p className="text-sm text-text-muted">{message}</p>
        <button
          type="button"
          onClick={() => {
            setStatus("loading");
            setMessage(null);
            requestSession().then(applySessionSuccess, applySessionError);
          }}
          className="rounded-sm border border-border px-3 py-2 text-sm font-semibold"
        >
          Reintentar
        </button>
      </section>
    );
  }

  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Panel</h1>
        <p className="text-sm text-text-muted">
          Sesión activa: {user?.name} ({user?.email})
        </p>
      </section>

      <OrganizationSelector onActiveOrganizationChange={setActiveOrganizationId} />
      <MembersPanel organizationId={activeOrganizationId} />

      <section aria-labelledby="recruitment-heading" className="space-y-2">
        <h2 id="recruitment-heading" className="text-sm font-semibold text-text-muted">
          Recruitment Core
        </h2>
        <ul className="flex flex-wrap gap-4 text-sm">
          <li>
            <a href="/jobs">Vacantes</a>
          </li>
          <li>
            <a href="/candidates">Candidatos</a>
          </li>
          <li>
            <a href="/applications">Pipeline</a>
          </li>
          <li>
            <a href="/documents">Documentos</a>
          </li>
          <li>
            <a href="/assessment">Evaluación</a>
          </li>
          <li>
            <a href="/agents">Agentes</a>
          </li>
        </ul>
      </section>
    </div>
  );
}
