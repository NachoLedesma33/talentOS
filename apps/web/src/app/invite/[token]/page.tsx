"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ACTIVE_ORG_STORAGE_KEY, ApiError, apiFetch } from "../../../lib/api";
import type {
  AuthResponse,
  InvitationAcceptResponse,
  InvitationDetailResponse,
  LoginRequest,
  MeResponse,
  RegisterRequest,
} from "../../../lib/types";
import { Button } from "../../../components/ui/shadcn/button";
import { Card } from "../../../components/ui/shadcn/card";
import { Checkbox } from "../../../components/ui/shadcn/checkbox";
import { Input } from "../../../components/ui/shadcn/input";
import { Label } from "../../../components/ui/shadcn/label";

type LoadStatus = "loading" | "ready" | "error";
type SessionMode = "unknown" | "anonymous" | "authenticated";
type AuthMode = "login" | "register";
type SubmitStatus = "idle" | "loading" | "error";

const ROLE_LABELS: Record<InvitationDetailResponse["role"], string> = {
  owner: "Propietario",
  admin: "Administrador",
  recruiter: "Reclutador",
  reviewer: "Revisor",
  viewer: "Observador",
};

function requestInvitation(encodedToken: string): Promise<InvitationDetailResponse> {
  return apiFetch<InvitationDetailResponse>(
    `/api/v1/organizations/invitations/${encodedToken}`,
  );
}

function requestSession(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/v1/auth/me");
}

export default function InvitationPage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const token = typeof params.token === "string" ? params.token : "";
  const encodedToken = encodeURIComponent(token);
  const [preview, setPreview] = useState<InvitationDetailResponse | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [session, setSession] = useState<SessionMode>("unknown");
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [status, setStatus] = useState<SubmitStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const applyPreview = useCallback(async (detail: InvitationDetailResponse) => {
    setPreview(detail);
    try {
      await requestSession();
      setSession("authenticated");
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSession("anonymous");
      } else {
        throw error;
      }
    }
    setLoadStatus("ready");
  }, []);

  const applyLoadError = useCallback((error: unknown) => {
    setSession("unknown");
    setLoadStatus("error");
    setMessage(
      error instanceof ApiError ? error.message : "No se pudo cargar la invitación.",
    );
  }, []);

  useEffect(() => {
    let active = true;
    requestInvitation(encodedToken).then(
      (detail) => {
        if (active) {
          void applyPreview(detail);
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
  }, [encodedToken, applyPreview, applyLoadError]);

  const acceptInvitation = useCallback(async () => {
    const response = await apiFetch<InvitationAcceptResponse>(
      `/api/v1/organizations/invitations/${encodedToken}/accept`,
      { method: "POST" },
    );
    window.localStorage.setItem(ACTIVE_ORG_STORAGE_KEY, response.organization_id);
    router.push("/dashboard");
  }, [encodedToken, router]);

  async function handleAccept() {
    setStatus("loading");
    setMessage(null);
    try {
      await acceptInvitation();
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError ? error.message : "No se pudo aceptar la invitación.",
      );
    }
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "").trim();
    setStatus("loading");
    setMessage(null);
    try {
      if (authMode === "login") {
        const payload: LoginRequest = { email, password: String(data.get("password") ?? "") };
        await apiFetch<AuthResponse>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      } else {
        const payload: RegisterRequest = {
          name: String(data.get("name") ?? "").trim(),
          email,
          password: String(data.get("password") ?? ""),
          accept_privacy: data.get("accept_privacy") === "true",
        };
        await apiFetch<AuthResponse>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify(payload),
        });
      }
      setSession("authenticated");
      await acceptInvitation();
    } catch (error) {
      setStatus("error");
      setMessage(
        error instanceof ApiError ? error.message : "No se pudo completar la invitación.",
      );
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md space-y-4">
        <div className="space-y-1">
          <Link href="/" className="text-sm font-semibold tracking-tight">
            TalentOS
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">Invitación al workspace</h1>
        </div>

        <Card className="space-y-4 p-5">
          {loadStatus === "loading" ? (
            <p role="status" aria-live="polite" className="text-sm text-text-muted">
              Cargando invitación…
            </p>
          ) : null}

          {loadStatus === "error" ? (
            <div className="space-y-3">
              <p role="alert" className="text-sm text-text-muted">
                Error: {message}
              </p>
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setLoadStatus("loading");
                  setMessage(null);
                  requestInvitation(encodedToken).then(
                    (detail) => void applyPreview(detail),
                    applyLoadError,
                  );
                }}
              >
                Reintentar
              </Button>
            </div>
          ) : null}

          {loadStatus === "ready" && preview ? (
            <>
              <dl className="space-y-2 text-sm">
                <div>
                  <dt className="text-text-muted">Organización</dt>
                  <dd className="font-medium">{preview.organization_name}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Correo invitado</dt>
                  <dd className="font-medium">{preview.email}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Rol</dt>
                  <dd className="font-medium">{ROLE_LABELS[preview.role] ?? preview.role}</dd>
                </div>
                <div>
                  <dt className="text-text-muted">Vigencia</dt>
                  <dd className="font-medium">
                    {new Date(preview.expires_at).toLocaleString("es-AR")}
                  </dd>
                </div>
              </dl>

              {session === "authenticated" ? (
                <div className="space-y-2">
                  <Button
                    type="button"
                    disabled={status === "loading"}
                    onClick={() => void handleAccept()}
                  >
                    {status === "loading" ? "Aceptando…" : "Aceptar invitación"}
                  </Button>
                  <p aria-live="assertive" role={status === "error" ? "alert" : undefined} className="min-h-5 text-sm text-text-muted">
                    {status === "error" ? `Error: ${message}` : null}
                  </p>
                </div>
              ) : null}

              {session === "anonymous" ? (
                <form onSubmit={handleAuthSubmit} aria-busy={status === "loading"} className="space-y-4">
                  <p className="text-sm text-text-muted">
                    Ingresá con el correo invitado para aceptar la invitación.
                  </p>

                  {authMode === "register" ? (
                    <div className="space-y-1">
                      <Label htmlFor="invite-name" className="block">
                        Nombre
                      </Label>
                      <Input id="invite-name" name="name" type="text" autoComplete="name" required />
                    </div>
                  ) : null}

                  <div className="space-y-1">
                    <Label htmlFor="invite-email" className="block">
                      Correo electrónico
                    </Label>
                    <Input
                      id="invite-email"
                      name="email"
                      type="email"
                      autoComplete="email"
                      defaultValue={preview.email}
                      required
                    />
                  </div>

                  <div className="space-y-1">
                    <Label htmlFor="invite-password" className="block">
                      Contraseña
                    </Label>
                    <Input
                      id="invite-password"
                      name="password"
                      type="password"
                      autoComplete={authMode === "login" ? "current-password" : "new-password"}
                      minLength={authMode === "register" ? 8 : undefined}
                      required
                    />
                  </div>

                  {authMode === "register" ? (
                    <div className="space-y-2">
                      <div className="flex items-start gap-2">
                        <Checkbox
                          id="invite-consent"
                          name="accept_privacy"
                          value="true"
                          aria-describedby="invite-consent-help"
                          required
                        />
                        <Label htmlFor="invite-consent" className="text-sm font-normal">
                          Acepto la política de privacidad y los términos de servicio.
                        </Label>
                      </div>
                      <p id="invite-consent-help" className="text-xs text-text-muted">
                        Revisá la{" "}
                        <a
                          href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/privacy-policy.md"
                          className="font-medium text-accent hover:opacity-80"
                        >
                          política de privacidad
                        </a>{" "}
                        y los{" "}
                        <a
                          href="https://github.com/NachoLedesma33/talentOS/blob/main/docs/terms-of-service.md"
                          className="font-medium text-accent hover:opacity-80"
                        >
                          términos de servicio
                        </a>
                        .
                      </p>
                    </div>
                  ) : null}

                  <Button type="submit" disabled={status === "loading"}>
                    {status === "loading"
                      ? "Procesando…"
                      : authMode === "login"
                        ? "Iniciar sesión y aceptar"
                        : "Crear cuenta y aceptar"}
                  </Button>

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAuthMode(authMode === "login" ? "register" : "login");
                      setStatus("idle");
                      setMessage(null);
                    }}
                  >
                    {authMode === "login" ? "Crear cuenta" : "Ya tengo cuenta"}
                  </Button>

                  <p
                    aria-live="assertive"
                    role={status === "error" ? "alert" : undefined}
                    className="min-h-5 text-sm text-text-muted"
                  >
                    {status === "error" ? `Error: ${message}` : null}
                  </p>
                </form>
              ) : null}
            </>
          ) : null}
        </Card>
      </div>
    </main>
  );
}
