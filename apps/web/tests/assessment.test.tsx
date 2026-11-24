import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssessmentComparison } from "../src/components/AssessmentComparison";
import { AssessmentPanel } from "../src/components/AssessmentPanel";
import { RequirementEvaluationCard } from "../src/components/RequirementEvaluationCard";
import type {
  Assessment,
  AssessmentComparison as AssessmentComparisonDto,
  RequirementEvaluation,
  ReviewDecision,
} from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const APPLICATION_ID = "11111111-1111-4111-8111-111111111111";
const ASSESSMENT_ID = "22222222-2222-4222-8222-222222222222";
const OTHER_ID = "33333333-3333-4333-8333-333333333333";
const REQUIREMENT_ID = "44444444-4444-4444-8444-444444444444";
const EVALUATION_ID = "55555555-5555-4555-8555-555555555555";
const DOCUMENT_ID = "66666666-6666-4666-8666-666666666666";
const REVIEWER_ID = "77777777-7777-4777-8777-777777777777";
const CREATED_AT = "2026-01-01T00:00:00Z";

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

function evidence() {
  return [
    {
      document_id: DOCUMENT_ID,
      field_name: "skills",
      page: 2,
      quote:
        "Skills: Python. Esta cita sintética se extiende lo suficiente para comprobar que la interfaz recorta el fragmento sin mostrar el texto completo.",
      offset: 12,
    },
  ];
}

function makeEvaluation(overrides: Partial<RequirementEvaluation> = {}): RequirementEvaluation {
  return {
    id: EVALUATION_ID,
    requirement_id: REQUIREMENT_ID,
    status: "supported",
    explanation: "Python confirmado en el campo skills.",
    evidence: evidence(),
    limitations: [],
    review_required: false,
    reviewed_by: null,
    reviewed_at: null,
    created_at: CREATED_AT,
    ...overrides,
  };
}

function makeAssessment(): Assessment {
  return {
    id: ASSESSMENT_ID,
    application_id: APPLICATION_ID,
    job_version_id: "88888888-8888-4888-8888-888888888888",
    candidate_id: "99999999-9999-4999-8999-999999999999",
    status: "needs_review",
    model_version: "matching-v1.0.0",
    prompt_version: "matching-v1",
    summary: {
      strengths: ["Evidencia confirmada de Python"],
      gaps: ["Sin evidencia de certificación"],
      questions: ["¿Proyecto con Python?"],
    },
    limitations: ["Fuente limitada a campos confirmados"],
    evaluations: [
      makeEvaluation(),
      makeEvaluation({
        id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        requirement_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        status: "not_found",
        explanation: "No se encontró evidencia de certificación.",
        evidence: [],
        limitations: ["Campo no confirmado"],
        review_required: true,
      }),
    ],
    review_required: true,
    created_at: CREATED_AT,
  };
}

function makeComparison(): AssessmentComparisonDto {
  return {
    base: {
      assessment_id: ASSESSMENT_ID,
      status: "completed",
      model_version: "matching-v1.0.0",
      prompt_version: "matching-v1",
    },
    target: {
      assessment_id: OTHER_ID,
      status: "needs_review",
      model_version: "matching-v1.1.0",
      prompt_version: "matching-v2",
    },
    changes: [
      {
        requirement_id: REQUIREMENT_ID,
        status: { before: "supported", after: "partial", changed: true },
        explanation: {
          before: "Python respaldado en skills",
          after: "Solo evidencia parcial de Python",
          changed: true,
        },
        evidence_refs: { before: evidence(), after: [], changed: true },
        review_required: { before: false, after: true, changed: true },
      },
    ],
  };
}

function fillAssessmentId(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

function submitForm(buttonName: string) {
  fireEvent.submit(screen.getByRole("button", { name: buttonName }).closest("form")!);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AssessmentPanel", () => {
  it("ejecuta, carga detalle y distingue una ejecución repetida", async () => {
    const posts: Array<{ application_id: string }> = [];
    const details: string[] = [];
    mockFetch((url, init) => {
      if (url.pathname === "/api/v1/assessment/run") {
        expect(init?.method).toBe("POST");
        posts.push(JSON.parse(String(init?.body)) as { application_id: string });
        return jsonResponse(makeAssessment(), posts.length === 1 ? 201 : 200);
      }
      if (url.pathname === `/api/v1/assessment/${ASSESSMENT_ID}`) {
        details.push(url.pathname);
        return jsonResponse(makeAssessment());
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AssessmentPanel />);
    fillAssessmentId("ID de postulación", APPLICATION_ID);
    submitForm("Evaluar postulación");

    expect(await screen.findByText("Evaluación creada.")).toBeTruthy();
    expect(posts).toEqual([{ application_id: APPLICATION_ID }]);
    expect(details).toHaveLength(1);
    expect(screen.getByText("Evidencia confirmada de Python")).toBeTruthy();
    expect(screen.getByText("Sin evidencia de certificación")).toBeTruthy();
    expect(screen.getByText("¿Proyecto con Python?")).toBeTruthy();
    expect(screen.getByText("Fuente limitada a campos confirmados")).toBeTruthy();
    expect(screen.getByText("matching-v1.0.0")).toBeTruthy();
    expect(screen.getByText("matching-v1")).toBeTruthy();
    expect(screen.getAllByText(/Requiere revisión humana/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Estado: Respaldado/)).toBeTruthy();
    expect(screen.getByText(/Estado: No encontrado/)).toBeTruthy();
    expect(screen.getByText(/Skills: Python/)).toBeTruthy();
    expect(screen.getByText(new RegExp(DOCUMENT_ID))).toBeTruthy();
    expect(screen.queryByText(/score|puntuación total|ranking/i)).toBeNull();

    submitForm("Evaluar postulación");

    expect(await screen.findByText("Evaluación existente recuperada.")).toBeTruthy();
    expect(posts).toHaveLength(2);
    expect(details).toHaveLength(2);
  });

  it("deshabilita el envío mientras la petición está pendiente", async () => {
    let resolveRun: (value: Response) => void = () => undefined;
    mockFetch((url) => {
      if (url.pathname === "/api/v1/assessment/run") {
        return new Promise<Response>((resolve) => {
          resolveRun = resolve;
        });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<AssessmentPanel />);
    fillAssessmentId("ID de postulación", APPLICATION_ID);
    submitForm("Evaluar postulación");

    const busyButton = screen.getByRole("button", { name: "Evaluando…" }) as HTMLButtonElement;
    expect(busyButton.disabled).toBe(true);
    expect(screen.getByText("Evaluando evidencia confirmada…")).toBeTruthy();

    resolveRun(jsonResponse(makeAssessment(), 201));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Evaluar postulación" })).toBeTruthy();
    });
  });
});

describe("RequirementEvaluationCard", () => {
  it("envía la corrección al servidor y muestra el revisor devuelto", async () => {
    const patches: ReviewDecision[] = [];
    mockFetch((url, init) => {
      if (
        url.pathname ===
        `/api/v1/assessment/${ASSESSMENT_ID}/evaluations/${EVALUATION_ID}/review`
      ) {
        expect(init?.method).toBe("PATCH");
        patches.push(JSON.parse(String(init?.body)) as ReviewDecision);
        return jsonResponse(
          makeEvaluation({
            status: "supported",
            explanation: "Corrección humana aplicada.",
            reviewed_by: REVIEWER_ID,
            reviewed_at: CREATED_AT,
          }),
        );
      }
      return errorResponse(404, "no encontrado");
    });

    const onReviewed = vi.fn();
    render(
      <RequirementEvaluationCard
        assessmentId={ASSESSMENT_ID}
        evaluation={makeEvaluation({ status: "partial" })}
        onReviewed={onReviewed}
      />,
    );

    fireEvent.change(screen.getByLabelText("Estado corregido"), {
      target: { value: "supported" },
    });
    fireEvent.change(screen.getByLabelText("Explicación (opcional)"), {
      target: { value: "Corrección humana aplicada." },
    });
    submitForm("Corregir revisión");

    expect(await screen.findByText("Revisión registrada: Respaldado.")).toBeTruthy();
    expect(patches).toEqual([
      { status: "supported", explanation: "Corrección humana aplicada." },
    ]);
    expect(onReviewed).toHaveBeenCalledTimes(1);
    expect(screen.getByText(new RegExp(REVIEWER_ID))).toBeTruthy();
  });

  it("muestra el 403 del servidor sin optimizar la revisión", async () => {
    mockFetch((url) => {
      if (
        url.pathname ===
        `/api/v1/assessment/${ASSESSMENT_ID}/evaluations/${EVALUATION_ID}/review`
      ) {
        return errorResponse(403, "Rol insuficiente.");
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <RequirementEvaluationCard
        assessmentId={ASSESSMENT_ID}
        evaluation={makeEvaluation({ status: "partial" })}
      />,
    );

    submitForm("Corregir revisión");

    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
    expect((screen.getByLabelText("Estado corregido") as HTMLSelectElement).value).toBe("partial");
    expect(screen.getAllByText(/Parcial/).length).toBeGreaterThan(0);
  });
});

describe("AssessmentComparison", () => {
  it("consulta la comparación y muestra estados, versiones y evidencia", async () => {
    const mock = mockFetch((url, init) => {
      expect(url.pathname).toBe(`/api/v1/assessment/${ASSESSMENT_ID}/compare`);
      expect(url.searchParams.get("other_id")).toBe(OTHER_ID);
      expect(init?.method).toBeUndefined();
      return jsonResponse(makeComparison());
    });

    render(<AssessmentComparison />);
    fillAssessmentId("Evaluación base", ASSESSMENT_ID);
    fillAssessmentId("Otra evaluación", OTHER_ID);
    submitForm("Comparar evaluaciones");

    expect(await screen.findByRole("table")).toBeTruthy();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Modelo: matching-v1\.0\.0/)).toBeTruthy();
    expect(screen.getByText(/Modelo: matching-v1\.1\.0/)).toBeTruthy();
    expect(screen.getByText(/Prompt: matching-v2/)).toBeTruthy();
    expect(screen.getByText(/Antes: Respaldado/)).toBeTruthy();
    expect(screen.getByText(/Después: Parcial/)).toBeTruthy();
    expect(screen.getByText(/Después: Solo evidencia parcial de Python/)).toBeTruthy();
    expect(screen.getByText(/Después: Sin evidencia verificable/)).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Evidencia" })).toBeTruthy();
    expect(screen.queryByText(/score|ranking/i)).toBeNull();
  });

  it.each([400, 404])("anuncia el error %i de comparación con role=alert", async (status) => {
    mockFetch(() =>
      errorResponse(
        status,
        status === 400
          ? "Las evaluaciones comparadas deben pertenecer a la misma postulación."
          : "Evaluación o postulación no encontrada.",
      ),
    );

    render(<AssessmentComparison />);
    fillAssessmentId("Evaluación base", ASSESSMENT_ID);
    fillAssessmentId("Otra evaluación", OTHER_ID);
    submitForm("Comparar evaluaciones");

    expect((await screen.findByRole("alert")).textContent).toContain(`${status}:`);
    expect(screen.queryByRole("table")).toBeNull();
  });
});
