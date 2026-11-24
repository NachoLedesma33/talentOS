import type { ErrorEnvelope } from "./types";

export const ACTIVE_ORG_STORAGE_KEY = "talentos:active-org";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

const GENERIC_ERROR_MESSAGE = "No se pudo completar la solicitud.";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, message: string, requestId?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseErrorEnvelope(value: unknown): ErrorEnvelope | null {
  if (!isRecord(value) || !isRecord(value.error)) {
    return null;
  }
  const { code, message, request_id: requestId } = value.error;
  if (typeof code !== "string" || typeof message !== "string") {
    return null;
  }
  return {
    error: {
      code,
      message,
      request_id: typeof requestId === "string" ? requestId : "unknown",
    },
  };
}

/**
 * Cliente HTTP único de la web. La sesión viaja en cookie HttpOnly;
 * localStorage sólo guarda la organización activa, nunca tokens.
 */
export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  // FormData define su propio boundary; fijar Content-Type rompería el multipart.
  if (
    options.body !== undefined &&
    !(typeof FormData !== "undefined" && options.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const activeOrganizationId =
    typeof window === "undefined" ? null : window.localStorage.getItem(ACTIVE_ORG_STORAGE_KEY);
  if (activeOrganizationId) {
    headers.set("X-Organization-ID", activeOrganizationId);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let envelope: ErrorEnvelope | null = null;
    try {
      envelope = parseErrorEnvelope(await response.json());
    } catch {
      envelope = null;
    }
    throw new ApiError(
      response.status,
      envelope?.error.code ?? "http_error",
      envelope?.error.message ?? GENERIC_ERROR_MESSAGE,
      envelope?.error.request_id,
    );
  }

  return (await response.json()) as T;
}
