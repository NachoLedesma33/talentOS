import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DocumentReview } from "../src/components/DocumentReview";
import { DocumentUpload } from "../src/components/DocumentUpload";
import type { Candidate, Document as DocumentDto, Extraction } from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response;

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(status: number, message: string): Response {
  return jsonResponse(
    { error: { code: "http_error", message, request_id: `req-${status}` } },
    status,
  );
}

function mockFetch(handler: FetchHandler) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function makeCandidate(): Candidate {
  return {
    id: "candidate-1",
    name: "Candidato Sintético",
    email: "candidate@example.test",
    location: null,
    profile_status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function makeDocument(): DocumentDto {
  return {
    id: "document-1",
    candidate_id: "candidate-1",
    original_filename: "cv.pdf",
    content_type: "application/pdf",
    extension: ".pdf",
    size_bytes: 128,
    checksum_sha256: "0".repeat(64),
    status: "processed",
    page_count: 1,
    created_at: "2026-01-01T00:00:00Z",
  };
}

function makeExtraction(overrides: Partial<Extraction> = {}): Extraction {
  return {
    id: "extraction-1",
    document_id: "document-1",
    provider: "mock",
    model: "mock-v1",
    prompt_version: "cv_extraction_v1",
    status: "completed",
    injection_detected: false,
    review_required: true,
    fields: [
      {
        id: "field-1",
        field_name: "email",
        value: "synthetic@example.test",
        status: "extracted",
        evidence: [
          {
            document_id: "document-1",
            page: 1,
            quote: "Email: synthetic@example.test",
            offset: 0,
          },
        ],
        confirmed_by: null,
        confirmed_at: null,
      },
      {
        id: "field-2",
        field_name: "projects",
        value: null,
        status: "needs_review",
        evidence: [],
        confirmed_by: null,
        confirmed_at: null,
      },
    ],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe("DocumentUpload", () => {
  it("sube multipart y solicita extracción", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url.pathname === "/api/v1/documents/upload") {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBeInstanceOf(FormData);
        expect((init?.headers as Headers).has("Content-Type")).toBe(false);
        return jsonResponse(makeDocument(), 201);
      }
      if (url.pathname === "/api/v1/documents/document-1/extract") {
        return jsonResponse({}, 202);
      }
      return errorResponse(404, "no encontrado");
    });

    render(<DocumentUpload candidates={[makeCandidate()]} />);
    fireEvent.change(screen.getByLabelText("Candidato"), {
      target: { value: "candidate-1" },
    });
    fireEvent.change(screen.getByLabelText("Archivo PDF o DOCX"), {
      target: {
        files: [new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" })],
      },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Subir y extraer" }).closest("form")!);

    await waitFor(() => {
      expect(screen.getByText("Documento cargado; extracción solicitada.")).toBeTruthy();
    });
    expect(
      fetchMock.mock.calls.some(
        ([input]) => new URL(String(input)).pathname === "/api/v1/documents/upload",
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([input]) =>
          new URL(String(input)).pathname === "/api/v1/documents/document-1/extract",
      ),
    ).toBe(true);
  });

  it("muestra error 400 y opción de reintento", async () => {
    mockFetch((url) => {
      if (url.pathname === "/api/v1/documents/upload") {
        return errorResponse(400, "Archivo inválido");
      }
      return errorResponse(404, "no encontrado");
    });

    render(<DocumentUpload candidates={[makeCandidate()]} />);
    fireEvent.change(screen.getByLabelText("Candidato"), {
      target: { value: "candidate-1" },
    });
    fireEvent.change(screen.getByLabelText("Archivo PDF o DOCX"), {
      target: {
        files: [new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" })],
      },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Subir y extraer" }).closest("form")!);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "400: Archivo inválido",
    );
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeTruthy();
  });
});

describe("DocumentReview", () => {
  it("carga campos, estado y evidencia acotada", async () => {
    mockFetch((url) => {
      if (url.pathname === "/api/v1/documents/document-1/extraction") {
        return jsonResponse(makeExtraction());
      }
      return errorResponse(404, "no encontrado");
    });

    render(<DocumentReview documentId="document-1" />);

    expect(await screen.findByText("synthetic@example.test")).toBeTruthy();
    expect(screen.getByText("Requiere revisión")).toBeTruthy();
    expect(screen.getByText(/Página 1: Email: synthetic@example.test/)).toBeTruthy();
  });

  it("muestra rechazo 403 a la confirmación", async () => {
    mockFetch((url, init) => {
      if (url.pathname === "/api/v1/documents/document-1/extraction") {
        return jsonResponse(makeExtraction());
      }
      if (
        url.pathname ===
        "/api/v1/documents/document-1/extraction/fields/field-1/confirm"
      ) {
        expect(init?.method).toBe("POST");
        return errorResponse(403, "Rol insuficiente.");
      }
      return errorResponse(404, "no encontrado");
    });

    render(<DocumentReview documentId="document-1" />);
    const confirmButtons = await screen.findAllByRole("button", { name: "Confirmar" });
    fireEvent.click(confirmButtons[0]);

    expect((await screen.findByRole("alert")).textContent).toContain(
      "403: Rol insuficiente.",
    );
  });

  it("avisa de inyección detectada", async () => {
    mockFetch((url) => {
      if (url.pathname === "/api/v1/documents/document-1/extraction") {
        return jsonResponse(
          makeExtraction({ injection_detected: true, review_required: true }),
        );
      }
      return errorResponse(404, "no encontrado");
    });

    render(<DocumentReview documentId="document-1" />);

    expect(await screen.findByText(/inyección de prompt/)).toBeTruthy();
  });
});
