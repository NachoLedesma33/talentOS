"use client";

import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  Member,
  MemberInvite,
  MemberRoleUpdate,
  MembershipRole,
} from "../lib/types";

const ROLES: readonly MembershipRole[] = [
  "owner",
  "admin",
  "recruiter",
  "reviewer",
  "viewer",
];

const INSUFFICIENT_MESSAGE = "Permisos insuficientes.";
const UNAUTHORIZED_MESSAGE = "Sesión caducada.";
const NOT_FOUND_MESSAGE = "No encontrado.";
const SERVER_ERROR_MESSAGE = "Error del servidor.";
const ACTION_IN_PROGRESS_MESSAGE = "Acción en curso…";

type LoadStatus =
  | "idle"
  | "loading"
  | "ready"
  | "forbidden"
  | "unauthorized"
  | "notFound"
  | "serverError"
  | "error";
type ActionStatus = "idle" | "loading" | "success" | "forbidden" | "error";

function statusFromError(error: unknown): "forbidden" | "error" {
  return error instanceof ApiError && error.status === 403 ? "forbidden" : "error";
}

function loadStatusFromError(error: unknown): LoadStatus {
  if (error instanceof ApiError) {
    if (error.status === 401) {
      return "unauthorized";
    }
    if (error.status === 403) {
      return "forbidden";
    }
    if (error.status === 404) {
      return "notFound";
    }
    if (error.status === 500) {
      return "serverError";
    }
  }
  return "error";
}

function messageFromError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 403) {
    return INSUFFICIENT_MESSAGE;
  }
  return error instanceof ApiError ? error.message : fallback;
}

function parseRole(value: string): MembershipRole | null {
  return ROLES.find((role) => role === value) ?? null;
}

function requestMembers(organizationId: string): Promise<Member[]> {
  return apiFetch<Member[]>(`/api/v1/organizations/${organizationId}/members`);
}

export function MembersPanel({ organizationId }: { organizationId: string | null }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("idle");
  const [loadMessage, setLoadMessage] = useState<string | null>(null);
  const [loadedOrganizationId, setLoadedOrganizationId] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<ActionStatus>("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionOrganizationId, setActionOrganizationId] = useState<string | null>(null);
  const [updatingMemberId, setUpdatingMemberId] = useState<string | null>(null);

  const applyMembersSuccess = useCallback(
    (items: Member[]) => {
      setLoadedOrganizationId(organizationId);
      setMembers(items);
      setLoadStatus("ready");
      setLoadMessage(items.length === 0 ? "Sin miembros en esta organización." : null);
    },
    [organizationId],
  );

  const applyMembersError = useCallback(
    (error: unknown) => {
      setLoadedOrganizationId(organizationId);
      setMembers([]);
      setLoadStatus(loadStatusFromError(error));
      setLoadMessage(messageFromError(error, "No se pudieron cargar los miembros."));
    },
    [organizationId],
  );

  useEffect(() => {
    if (!organizationId) {
      return;
    }
    let active = true;
    requestMembers(organizationId).then(
      (items) => {
        if (active) {
          applyMembersSuccess(items);
        }
      },
      (error: unknown) => {
        if (active) {
          applyMembersError(error);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [organizationId, applyMembersSuccess, applyMembersError]);

  async function handleInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organizationId) {
      return;
    }
    const form = event.currentTarget;
    const data = new FormData(form);
    const role = parseRole(String(data.get("role") ?? ""));
    if (!role) {
      setActionStatus("error");
      setActionMessage("Selecciona un rol válido.");
      return;
    }
    const payload: MemberInvite = {
      email: String(data.get("email") ?? "").trim(),
      role,
    };

    setActionOrganizationId(organizationId);
    setActionStatus("loading");
    setActionMessage(null);
    try {
      await apiFetch<Member>(`/api/v1/organizations/${organizationId}/members`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      setActionStatus("success");
      setActionMessage("Miembro invitado.");
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } catch (error) {
      setActionStatus(statusFromError(error));
      setActionMessage(messageFromError(error, "No se pudo invitar al miembro."));
    }
  }

  async function handleRoleChange(member: Member, event: ChangeEvent<HTMLSelectElement>) {
    if (!organizationId) {
      return;
    }
    const role = parseRole(event.target.value);
    if (!role || role === member.role) {
      return;
    }
    const payload: MemberRoleUpdate = { role };

    setActionOrganizationId(organizationId);
    setUpdatingMemberId(member.user_id);
    setActionStatus("loading");
    setActionMessage(null);
    try {
      await apiFetch<Member>(
        `/api/v1/organizations/${organizationId}/members/${member.user_id}`,
        { method: "PATCH", body: JSON.stringify(payload) },
      );
      setActionStatus("success");
      setActionMessage("Rol actualizado.");
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } catch (error) {
      setActionStatus(statusFromError(error));
      setActionMessage(messageFromError(error, "No se pudo actualizar el rol."));
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } finally {
      setUpdatingMemberId(null);
    }
  }

  if (!organizationId) {
    return (
      <section aria-labelledby="members-heading" className="space-y-2">
        <h2 id="members-heading" className="text-lg font-semibold">
          Miembros
        </h2>
        <p className="text-sm text-text-muted">
          Selecciona una organización para ver sus miembros.
        </p>
      </section>
    );
  }

  const visibleLoadStatus: LoadStatus =
    loadedOrganizationId === organizationId ? loadStatus : "loading";
  const visibleActionStatus: ActionStatus =
    actionOrganizationId === organizationId ? actionStatus : "idle";
  const visibleActionMessage =
    actionOrganizationId === organizationId ? actionMessage : null;
  const busy = visibleActionStatus === "loading" || updatingMemberId !== null;
  const actionAnnouncementRole =
    visibleActionStatus === "forbidden" || visibleActionStatus === "error"
      ? "alert"
      : busy || visibleActionMessage
        ? "status"
        : undefined;

  return (
    <section aria-labelledby="members-heading" className="space-y-3">
      <h2 id="members-heading" className="text-lg font-semibold">
        Miembros
      </h2>

      <div aria-live="polite">
        {visibleLoadStatus === "loading" ? (
          <p role="status" className="text-sm text-text-muted">
            Cargando miembros…
          </p>
        ) : null}
        {visibleLoadStatus === "forbidden" ? (
          <p role="alert" className="text-sm text-text-muted">
            {INSUFFICIENT_MESSAGE}
          </p>
        ) : null}
        {visibleLoadStatus === "unauthorized" ? (
          <p role="alert" className="text-sm text-text-muted">
            {UNAUTHORIZED_MESSAGE}
          </p>
        ) : null}
        {visibleLoadStatus === "notFound" ? (
          <p role="alert" className="text-sm text-text-muted">
            {NOT_FOUND_MESSAGE}
          </p>
        ) : null}
        {visibleLoadStatus === "serverError" ? (
          <p role="alert" className="text-sm text-text-muted">
            {SERVER_ERROR_MESSAGE}
          </p>
        ) : null}
        {visibleLoadStatus === "error" ? (
          <p role="alert" className="text-sm text-text-muted">
            {loadMessage}
          </p>
        ) : null}
        {visibleLoadStatus === "ready" && members.length === 0 ? (
          <p className="text-sm text-text-muted">{loadMessage}</p>
        ) : null}
      </div>

      {visibleLoadStatus === "ready" && members.length > 0 ? (
        <ul className="space-y-2">
          {members.map((member) => (
            <li
              key={member.user_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-border px-3 py-2"
            >
              <div className="space-y-0">
                <p className="text-sm font-semibold">{member.name}</p>
                <p className="text-xs text-text-muted">{member.email}</p>
              </div>
              <div className="space-y-1">
                <label
                  htmlFor={`member-role-${member.user_id}`}
                  className="block text-xs text-text-muted"
                >
                  Rol
                </label>
                <select
                  id={`member-role-${member.user_id}`}
                  aria-label={`Rol de ${member.name}`}
                  value={member.role}
                  disabled={busy}
                  onChange={(event) => {
                    void handleRoleChange(member, event);
                  }}
                  className="rounded-sm border border-border bg-surface px-2 py-1 text-sm"
                >
                  {ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
            </li>
          ))}
        </ul>
      ) : null}

      <form
        onSubmit={handleInvite}
        aria-busy={visibleActionStatus === "loading"}
        className="space-y-3"
      >
        <h3 className="text-sm font-semibold">Invitar miembro</h3>
        <div className="space-y-1">
          <label htmlFor="invite-email" className="block text-sm font-semibold">
            Correo electrónico
          </label>
          <input
            id="invite-email"
            name="email"
            type="email"
            required
            disabled={busy}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        </div>
        <div className="space-y-1">
          <label htmlFor="invite-role" className="block text-sm font-semibold">
            Rol
          </label>
          <select
            id="invite-role"
            name="role"
            defaultValue="viewer"
            disabled={busy}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-sm bg-accent px-4 py-2 text-sm font-semibold text-on-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {visibleActionStatus === "loading" && updatingMemberId === null
            ? "Invitando…"
            : "Invitar miembro"}
        </button>
        <p
          aria-live="polite"
          role={actionAnnouncementRole}
          className="min-h-5 text-sm text-text-muted"
        >
          {visibleActionMessage ?? (busy ? ACTION_IN_PROGRESS_MESSAGE : null)}
        </p>
      </form>
    </section>
  );
}
