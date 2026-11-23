"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
} from "react";
import { ACTIVE_ORG_STORAGE_KEY, ApiError, apiFetch } from "../lib/api";
import type { Organization } from "../lib/types";

type LoadStatus = "loading" | "ready" | "error";

type OrganizationSelectorProps = {
  onActiveOrganizationChange?: (organizationId: string) => void;
};

function requestOrganizations(): Promise<Organization[]> {
  return apiFetch<Organization[]>("/api/v1/organizations");
}

export function OrganizationSelector({
  onActiveOrganizationChange,
}: OrganizationSelectorProps) {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeId, setActiveId] = useState("");
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [message, setMessage] = useState<string | null>(null);
  const onChangeRef = useRef(onActiveOrganizationChange);

  useEffect(() => {
    onChangeRef.current = onActiveOrganizationChange;
  }, [onActiveOrganizationChange]);

  const applyOrganizations = useCallback((items: Organization[]) => {
    const storedId = window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
    const selectedId = items.some((item) => item.id === storedId)
      ? (storedId ?? "")
      : (items[0]?.id ?? "");

    if (selectedId && selectedId !== storedId) {
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, selectedId);
    }
    setOrganizations(items);
    setActiveId(selectedId);
    setStatus("ready");
    setMessage(items.length === 0 ? "Sin organizaciones disponibles." : null);
  }, []);

  const applyLoadError = useCallback((error: unknown) => {
    setStatus("error");
    setMessage(
      error instanceof ApiError
        ? error.message
        : "No se pudieron cargar las organizaciones.",
    );
  }, []);

  useEffect(() => {
    let active = true;
    requestOrganizations().then(
      (items) => {
        if (active) {
          applyOrganizations(items);
        }
      },
      (error: unknown) => {
        if (active) {
          applyLoadError(error);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [applyOrganizations, applyLoadError]);

  useEffect(() => {
    if (activeId) {
      onChangeRef.current?.(activeId);
    }
  }, [activeId]);

  function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextId = event.target.value;
    setActiveId(nextId);
    if (nextId) {
      window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, nextId);
    }
  }

  return (
    <section aria-labelledby="organization-selector-heading" className="space-y-2">
      <h2 id="organization-selector-heading" className="text-lg font-semibold">
        Organización activa
      </h2>

      {status === "loading" ? (
        <p role="status" aria-live="polite" className="text-sm text-text-muted">
          Cargando organizaciones…
        </p>
      ) : null}

      {status === "error" ? (
        <div className="space-y-2" role="alert">
          <p className="text-sm text-text-muted">{message}</p>
          <button
            type="button"
            onClick={() => {
              setStatus("loading");
              setMessage(null);
              requestOrganizations().then(applyOrganizations, applyLoadError);
            }}
            className="rounded-sm border border-border px-3 py-1 text-sm font-semibold"
          >
            Reintentar
          </button>
        </div>
      ) : null}

      {status === "ready" && organizations.length > 0 ? (
        <select
          aria-label="Organización activa"
          value={activeId}
          onChange={handleChange}
          className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
        >
          {organizations.map((organization) => (
            <option key={organization.id} value={organization.id}>
              {organization.name}
            </option>
          ))}
        </select>
      ) : null}

      {status === "ready" && organizations.length === 0 ? (
        <p aria-live="polite" className="text-sm text-text-muted">
          {message}
        </p>
      ) : null}
    </section>
  );
}
