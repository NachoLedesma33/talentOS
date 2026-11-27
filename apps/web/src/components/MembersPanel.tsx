"use client";

import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  Member,
  MemberInvite,
  MemberRoleUpdate,
  MembershipRole,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

const ROLES: readonly MembershipRole[] = [
  "owner",
  "admin",
  "recruiter",
  "reviewer",
  "viewer",
];

type Translate = (key: MessageKey) => string;

const INSUFFICIENT_KEY: MessageKey = "members.insufficient";
const UNAUTHORIZED_KEY: MessageKey = "members.unauthorized";
const NOT_FOUND_KEY: MessageKey = "members.notFound";
const SERVER_ERROR_KEY: MessageKey = "members.serverError";
const ACTION_IN_PROGRESS_KEY: MessageKey = "members.busy";

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

function messageFromError(error: unknown, fallback: string, t: Translate): string {
  if (error instanceof ApiError && error.status === 403) {
    return t(INSUFFICIENT_KEY);
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
  const { t } = useI18n();
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
      setLoadMessage(items.length === 0 ? t("members.empty") : null);
    },
    [organizationId, t],
  );

  const applyMembersError = useCallback(
    (error: unknown) => {
      setLoadedOrganizationId(organizationId);
      setMembers([]);
      setLoadStatus(loadStatusFromError(error));
      setLoadMessage(messageFromError(error, t("members.loadError"), t));
    },
    [organizationId, t],
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
      setActionMessage(t("members.invalidRole"));
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
      setActionMessage(t("members.invited"));
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } catch (error) {
      setActionStatus(statusFromError(error));
      setActionMessage(messageFromError(error, t("members.inviteError"), t));
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
      setActionMessage(t("members.roleUpdated"));
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } catch (error) {
      setActionStatus(statusFromError(error));
      setActionMessage(messageFromError(error, t("members.roleUpdateError"), t));
      await requestMembers(organizationId).then(applyMembersSuccess, applyMembersError);
    } finally {
      setUpdatingMemberId(null);
    }
  }

  if (!organizationId) {
    return (
      <section aria-labelledby="members-heading" className="space-y-2">
        <h2 id="members-heading" className="text-lg font-semibold">
          {t("members.title")}
        </h2>
        <p className="text-sm text-text-muted">
          {t("members.selectOrg")}
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
        {t("members.title")}
      </h2>

      <div aria-live="polite">
        {visibleLoadStatus === "loading" ? (
          <p role="status" className="text-sm text-text-muted">
            {t("members.loading")}
          </p>
        ) : null}
        {visibleLoadStatus === "forbidden" ? (
          <p role="alert" className="text-sm text-text-muted">
            {t(INSUFFICIENT_KEY)}
          </p>
        ) : null}
        {visibleLoadStatus === "unauthorized" ? (
          <p role="alert" className="text-sm text-text-muted">
            {t(UNAUTHORIZED_KEY)}
          </p>
        ) : null}
        {visibleLoadStatus === "notFound" ? (
          <p role="alert" className="text-sm text-text-muted">
            {t(NOT_FOUND_KEY)}
          </p>
        ) : null}
        {visibleLoadStatus === "serverError" ? (
          <p role="alert" className="text-sm text-text-muted">
            {t(SERVER_ERROR_KEY)}
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
            <li key={member.user_id}>
              <Card className="flex flex-wrap items-center justify-between gap-3 p-3">
                <div className="space-y-0">
                  <p className="text-sm font-semibold">{member.name}</p>
                  <p className="text-xs text-text-muted">{member.email}</p>
                </div>
                <div className="space-y-1">
                  <Label
                    htmlFor={`member-role-${member.user_id}`}
                    className="block text-xs text-text-muted"
                  >
                    {t("members.role")}
                  </Label>
                  <Select
                    id={`member-role-${member.user_id}`}
                    aria-label={`${t("members.roleFor")}${member.name}`}
                    value={member.role}
                    disabled={busy}
                    onChange={(event) => {
                      void handleRoleChange(member, event);
                    }}
                    className="h-9 w-auto"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </Select>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}

      <form
        onSubmit={handleInvite}
        aria-busy={visibleActionStatus === "loading"}
        className="space-y-3"
      >
        <h3 className="text-sm font-semibold">{t("members.inviteTitle")}</h3>
        <div className="space-y-1">
          <Label htmlFor="invite-email" className="block">
            {t("members.email")}
          </Label>
          <Input
            id="invite-email"
            name="email"
            type="email"
            required
            disabled={busy}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="invite-role" className="block">
            {t("members.role")}
          </Label>
          <Select
            id="invite-role"
            name="role"
            defaultValue="viewer"
            disabled={busy}
          >
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </Select>
        </div>
        <Button type="submit" disabled={busy}>
          {visibleActionStatus === "loading" && updatingMemberId === null
            ? t("members.inviting")
            : t("members.inviteTitle")}
        </Button>
        <p
          aria-live="polite"
          role={actionAnnouncementRole}
          className="min-h-5 text-sm text-text-muted"
        >
          {visibleActionMessage ?? (busy ? t(ACTION_IN_PROGRESS_KEY) : null)}
        </p>
      </form>
    </section>
  );
}
