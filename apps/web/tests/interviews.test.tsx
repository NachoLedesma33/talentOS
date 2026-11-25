import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeedbackForm } from "../src/components/FeedbackForm";
import { GuideHistory } from "../src/components/GuideHistory";
import { InterviewGuidePanel } from "../src/components/InterviewGuidePanel";
import { QuestionEditor } from "../src/components/QuestionEditor";
import type {
  GuideGeneration,
  GuideRevisionList,
  InterviewFeedback,
  InterviewFeedbackList,
  InterviewGuideDetail,
  InterviewGuideList,
  InterviewGuideSummary,
  InterviewQuestion,
} from "../src/lib/types";

type FetchHandler = (url: URL, init?: RequestInit) => Response | Promise<Response>;

const APPLICATION_ID = "11111111-1111-4111-8111-111111111111";
const GUIDE_ID = "22222222-2222-4222-8222-222222222222";
const SECOND_GUIDE_ID = "22222222-2222-4222-8222-222222222223";
const QUESTION_ID = "33333333-3333-4333-8333-333333333333";
const REQUIREMENT_ID = "44444444-4444-4444-8444-444444444444";
const INTERVIEWER_ID = "55555555-5555-4555-8555-555555555555";
const FEEDBACK_ID = "66666666-6666-4666-8666-666666666666";
const REVISION_ID = "77777777-7777-4777-8777-777777777777";
const MODEL_VERSION = "interview-mock-v1";
const PROMPT_VERSION = "interview-v1";
const CREATED_AT = "2026-02-01T10:00:00Z";
const CV_MARKER = "CV-SINTETICO-NO-DEBE-APARECER";
const SECRET_MARKER = "sk-sintetico-no-debe-aparecer";
const GUIDES_PATH = "/api/v1/interviews/guides";

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(
  status: number,
  message: string,
  code = "http_error",
  reasonCode?: string,
): Response {
  return jsonResponse(
    {
      error: {
        code,
        message,
        request_id: `req-${status}`,
        ...(reasonCode ? { reason_code: reasonCode } : {}),
      },
    },
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

function parseBody(init?: RequestInit): Record<string, unknown> {
  return JSON.parse(String(init?.body)) as Record<string, unknown>;
}

function makeQuestion(overrides: Partial<InterviewQuestion> = {}): InterviewQuestion {
  return {
    id: QUESTION_ID,
    requirement_id: REQUIREMENT_ID,
    category: "technical",
    question: "¿Qué experiencia técnica demuestra el proyecto?",
    evidence_focus: "Experiencia profesional verificable",
    competency: "Resolución de problemas",
    status: "draft",
    position: 1,
    review_required: true,
    model_version: MODEL_VERSION,
    prompt_version: PROMPT_VERSION,
    ...overrides,
  };
}

function makeSummary(overrides: Partial<InterviewGuideSummary> = {}): InterviewGuideSummary {
  return {
    id: GUIDE_ID,
    application_id: APPLICATION_ID,
    title: "Guía sintética v1",
    status: "draft",
    version: 1,
    created_at: CREATED_AT,
    updated_at: CREATED_AT,
    ...overrides,
  };
}

function makeDetail(overrides: Partial<InterviewGuideDetail> = {}): InterviewGuideDetail {
  return {
    ...makeSummary(),
    job_version_id: "88888888-8888-4888-8888-888888888888",
    model_version: MODEL_VERSION,
    prompt_version: PROMPT_VERSION,
    limitations: ["limitacion-sintetica"],
    review_required: true,
    needs_review: true,
    questions: [makeQuestion()],
    ...overrides,
  };
}

function makeGeneration(overrides: Partial<GuideGeneration> = {}): GuideGeneration {
  return {
    guide_id: GUIDE_ID,
    application_id: APPLICATION_ID,
    version: 1,
    status: "draft",
    model_version: MODEL_VERSION,
    prompt_version: PROMPT_VERSION,
    job_version_id: "88888888-8888-4888-8888-888888888888",
    questions: [makeQuestion()],
    rejected_questions: [],
    limitations: ["limitacion-sintetica"],
    review_required: true,
    needs_review: true,
    created: true,
    ...overrides,
  };
}

function makeGuideList(items: InterviewGuideSummary[] = [makeSummary()]): InterviewGuideList {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function makeFeedback(overrides: Partial<InterviewFeedback> = {}): InterviewFeedback {
  return {
    id: FEEDBACK_ID,
    question_id: QUESTION_ID,
    requirement_id: REQUIREMENT_ID,
    interviewer_id: INTERVIEWER_ID,
    status: "submitted",
    observed_evidence: ["Evidencia observada sintética"],
    gaps: ["Brecha sintética"],
    follow_up_needed: true,
    notes: "Nota sintética",
    submitted_at: CREATED_AT,
    created_at: CREATED_AT,
    ...overrides,
  };
}

function makeFeedbackList(items: InterviewFeedback[] = [makeFeedback()]): InterviewFeedbackList {
  return { items, total: items.length, limit: 50, offset: 0 };
}

function makeRevisionList(snapshot: Record<string, unknown>): GuideRevisionList {
  return {
    items: [
      {
        id: REVISION_ID,
        version: 1,
        created_by: INTERVIEWER_ID,
        created_at: CREATED_AT,
        snapshot,
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  };
}

function fillAndSubmitApplication(): void {
  fireEvent.change(screen.getByLabelText("ID de postulación"), {
    target: { value: APPLICATION_ID },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Generar guía" }).closest("form")!,
  );
}

async function openGeneratedGuide(): Promise<void> {
  fillAndSubmitApplication();
  expect(await screen.findByText(/Guía creada\.|Guía existente recuperada\./)).toBeTruthy();
}

function fillNewQuestionForm(): void {
  fireEvent.change(screen.getByLabelText("ID de requisito"), {
    target: { value: REQUIREMENT_ID },
  });
  fireEvent.change(screen.getByLabelText("Competencia"), {
    target: { value: "Resolución de problemas" },
  });
  fireEvent.change(screen.getByLabelText("Pregunta"), {
    target: { value: CV_MARKER },
  });
  fireEvent.change(screen.getByLabelText("Foco de evidencia"), {
    target: { value: "Experiencia profesional verificable" },
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("InterviewGuidePanel", () => {
  it("genera con 201, lista guías y carga detalle sin PII", async () => {
    const posts: Array<Record<string, unknown>> = [];
    mockFetch((url, init) => {
      if (url.pathname === `${GUIDES_PATH}/generate` && init?.method === "POST") {
        posts.push(parseBody(init));
        return jsonResponse(
          makeGeneration({
            limitations: [CV_MARKER, SECRET_MARKER],
          }),
          201,
        );
      }
      if (url.pathname === GUIDES_PATH) {
        return jsonResponse(
          makeGuideList([
            makeSummary(),
            makeSummary({
              id: SECOND_GUIDE_ID,
              title: "Guía sintética v2",
              version: 2,
            }),
          ]),
        );
      }
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}`) {
        return jsonResponse(
          {
            ...makeDetail({ limitations: [CV_MARKER], questions: [makeQuestion()] }),
            cv_text: CV_MARKER,
            secret: SECRET_MARKER,
          } as unknown as InterviewGuideDetail,
        );
      }
      if (url.pathname === `${GUIDES_PATH}/${SECOND_GUIDE_ID}`) {
        return jsonResponse(
          makeDetail({
            id: SECOND_GUIDE_ID,
            title: "Guía sintética v2",
            version: 2,
            review_required: false,
            needs_review: false,
          }),
        );
      }
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/revisions`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<InterviewGuidePanel />);
    await openGeneratedGuide();

    expect(posts).toEqual([{ application_id: APPLICATION_ID }]);
    expect(screen.getByText("Guía creada.")).toBeTruthy();
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(screen.getByText(MODEL_VERSION)).toBeTruthy();
    expect(screen.getByText(PROMPT_VERSION)).toBeTruthy();
    expect(screen.getByText("Revisión requerida: sí")).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain(CV_MARKER);
    expect(text).not.toContain(SECRET_MARKER);

    fireEvent.click(screen.getByRole("button", { name: /v2/ }));
    expect(await screen.findByText("Revisión requerida: no")).toBeTruthy();
  });

  it("reutiliza una guía existente con 200", async () => {
    mockFetch((url, init) => {
      if (url.pathname === `${GUIDES_PATH}/generate` && init?.method === "POST") {
        return jsonResponse(makeGeneration({ created: false }), 200);
      }
      if (url.pathname === GUIDES_PATH) return jsonResponse(makeGuideList());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}`) return jsonResponse(makeDetail());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/revisions`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<InterviewGuidePanel />);
    await openGeneratedGuide();
    expect(screen.getByText("Guía existente recuperada.")).toBeTruthy();
  });

  it("muestra el 409 de publicación sin optimizar el estado local", async () => {
    let patchBody: Record<string, unknown> | null = null;
    mockFetch((url, init) => {
      if (url.pathname === `${GUIDES_PATH}/generate`) {
        return jsonResponse(makeGeneration(), 201);
      }
      if (url.pathname === GUIDES_PATH) return jsonResponse(makeGuideList());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}` && init?.method === "PATCH") {
        patchBody = parseBody(init);
        return errorResponse(409, "No se puede publicar: quedan preguntas pendientes.");
      }
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}`) return jsonResponse(makeDetail());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/revisions`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<InterviewGuidePanel />);
    await openGeneratedGuide();
    fireEvent.click(screen.getByRole("button", { name: "Publicar guía" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("409:");
    expect(alert.textContent).toContain("No se puede publicar");
    expect(patchBody).toEqual({ status: "published" });
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Publicar guía" }).hasAttribute("disabled")).toBe(
      false,
    );
  });

  it("publica con 200 y refleja el estado devuelto", async () => {
    mockFetch((url, init) => {
      if (url.pathname === `${GUIDES_PATH}/generate`) {
        return jsonResponse(makeGeneration(), 201);
      }
      if (url.pathname === GUIDES_PATH) return jsonResponse(makeGuideList());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}` && init?.method === "PATCH") {
        return jsonResponse(makeDetail({ status: "published", needs_review: false }));
      }
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}`) return jsonResponse(makeDetail());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/revisions`) {
        return jsonResponse({ items: [], total: 0, limit: 50, offset: 0 });
      }
      return errorResponse(404, "no encontrado");
    });

    render(<InterviewGuidePanel />);
    await openGeneratedGuide();
    fireEvent.click(screen.getByRole("button", { name: "Publicar guía" }));

    expect(await screen.findByText("Guía publicada.")).toBeTruthy();
    expect(screen.getByText("Publicada")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Guía ya publicada" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("hace visible el 403 del servidor", async () => {
    mockFetch(() => errorResponse(403, "Rol insuficiente."));
    render(<InterviewGuidePanel />);
    fillAndSubmitApplication();
    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
  });

  it("hace visible el 404 cross-tenant al cargar el detalle", async () => {
    mockFetch((url) => {
      if (url.pathname === `${GUIDES_PATH}/generate`) {
        return jsonResponse(makeGeneration(), 201);
      }
      if (url.pathname === GUIDES_PATH) return jsonResponse(makeGuideList());
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}`) {
        return errorResponse(404, "Guía, pregunta o postulación no encontrada.");
      }
      return errorResponse(404, "no encontrado");
    });
    render(<InterviewGuidePanel />);
    fillAndSubmitApplication();
    expect((await screen.findByRole("alert")).textContent).toContain(
      "404: Guía, pregunta o postulación no encontrada.",
    );
    expect(screen.queryByText("Preguntas")).toBeNull();
  });
});

describe("QuestionEditor", () => {
  it("crea una pregunta con 201 y notifica el cambio", async () => {
    const bodies: Array<Record<string, unknown>> = [];
    const onChanged = vi.fn();
    mockFetch((url, init) => {
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/questions` && init?.method === "POST") {
        bodies.push(parseBody(init));
        return jsonResponse(makeQuestion(), 201);
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
        onChanged={onChanged}
      />,
    );
    fillNewQuestionForm();
    fireEvent.click(screen.getByLabelText("Requiere revisión humana"));
    fireEvent.submit(
      screen.getByRole("button", { name: "Agregar pregunta" }).closest("form")!,
    );

    expect(await screen.findByText("Pregunta agregada.")).toBeTruthy();
    expect(bodies).toEqual([
      {
        requirement_id: REQUIREMENT_ID,
        position: 1,
        category: "technical",
        question: CV_MARKER,
        evidence_focus: "Experiencia profesional verificable",
        competency: "Resolución de problemas",
        review_required: true,
        model_version: MODEL_VERSION,
        prompt_version: PROMPT_VERSION,
      },
    ]);
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: QUESTION_ID }));
  });

  it("muestra el reason_code del 422 sin devolver texto sensible", async () => {
    mockFetch((url) => {
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/questions`) {
        return errorResponse(
          422,
          "La pregunta no cumple la política de selección.",
          "policy_rejected",
          "protected_attribute_proxy",
        );
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
      />,
    );
    fillNewQuestionForm();
    fireEvent.submit(
      screen.getByRole("button", { name: "Agregar pregunta" }).closest("form")!,
    );

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("422:");
    expect(alert.textContent).toContain("Motivo de política: protected_attribute_proxy");
    expect(alert.textContent).not.toContain(CV_MARKER);
  });

  it("edita y reordena con PATCH sin enviar reglas de negocio", async () => {
    let patchBody: Record<string, unknown> | null = null;
    const onChanged = vi.fn();
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}` && init?.method === "PATCH") {
        patchBody = parseBody(init);
        return jsonResponse(makeQuestion({ position: 3, status: "approved" }));
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[makeQuestion()]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Editar pregunta" }));
    fireEvent.change(screen.getByLabelText(`Posición ${QUESTION_ID}`), {
      target: { value: "3" },
    });
    fireEvent.change(screen.getByLabelText(`Estado ${QUESTION_ID}`), {
      target: { value: "approved" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Guardar pregunta" }).closest("form")!);

    expect(await screen.findByText("Pregunta actualizada.")).toBeTruthy();
    expect(patchBody).toEqual({
      question: "¿Qué experiencia técnica demuestra el proyecto?",
      evidence_focus: "Experiencia profesional verificable",
      competency: "Resolución de problemas",
      position: 3,
      status: "approved",
    });
    expect(patchBody).not.toHaveProperty("category");
    expect(patchBody).not.toHaveProperty("review_required");
    expect(onChanged).toHaveBeenCalledWith(
      expect.objectContaining({ position: 3, status: "approved" }),
    );
  });

  it("muestra el 409 del servidor al reordenar", async () => {
    mockFetch((url) => {
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}`) {
        return errorResponse(409, "El recurso cambió; recárguelo y reintente.");
      }
      return errorResponse(404, "no encontrado");
    });
    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[makeQuestion()]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Editar pregunta" }));
    fireEvent.submit(screen.getByRole("button", { name: "Guardar pregunta" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toContain(
      "409: El recurso cambió; recárguelo y reintente.",
    );
  });

  it("archiva sólo después de confirmación explícita", async () => {
    const confirmMock = vi.fn(() => false);
    vi.stubGlobal("confirm", confirmMock);
    const methods: string[] = [];
    const onChanged = vi.fn();
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}`) {
        methods.push(String(init?.method));
        return jsonResponse(makeQuestion({ status: "archived" }));
      }
      return errorResponse(404, "no encontrado");
    });

    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[makeQuestion()]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Archivar pregunta" }));
    expect(methods).toEqual([]);
    expect(confirmMock).toHaveBeenCalledTimes(1);

    confirmMock.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Archivar pregunta" }));
    expect(await screen.findByText("Pregunta archivada.")).toBeTruthy();
    expect(methods).toEqual(["DELETE"]);
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "archived" }));
  });

  it("muestra el 403 de reviewer al editar sin aplicar cambios locales", async () => {
    const onChanged = vi.fn();
    mockFetch((url) => {
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}`) {
        return errorResponse(403, "Rol insuficiente.");
      }
      return errorResponse(404, "no encontrado");
    });
    render(
      <QuestionEditor
        guideId={GUIDE_ID}
        questions={[makeQuestion()]}
        modelVersion={MODEL_VERSION}
        promptVersion={PROMPT_VERSION}
        onChanged={onChanged}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Editar pregunta" }));
    fireEvent.submit(screen.getByRole("button", { name: "Guardar pregunta" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
    expect(screen.getAllByText("Borrador").length).toBeGreaterThan(0);
    expect(onChanged).not.toHaveBeenCalled();
  });
});

describe("FeedbackForm", () => {
  it("registra feedback vinculado al requisito con listas acotadas e historial", async () => {
    let postBody: Record<string, unknown> | null = null;
    mockFetch((url, init) => {
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}/feedback`) {
        if (init?.method === "POST") {
          postBody = parseBody(init);
          return jsonResponse(makeFeedback(), 201);
        }
        return jsonResponse(makeFeedbackList());
      }
      return errorResponse(404, "no encontrado");
    });

    render(<FeedbackForm questionId={QUESTION_ID} requirementId={REQUIREMENT_ID} />);
    fireEvent.change(screen.getByLabelText(/Evidencia observada/), {
      target: { value: "Evidencia uno\nEvidencia dos" },
    });
    fireEvent.change(screen.getByLabelText(/Brechas/), {
      target: { value: "Brecha uno" },
    });
    fireEvent.click(screen.getByLabelText("Requiere seguimiento"));
    fireEvent.change(screen.getByLabelText("Notas opcionales"), {
      target: { value: "Nota sintética" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Registrar feedback" }).closest("form")!);

    expect(await screen.findByText("Feedback registrado.")).toBeTruthy();
    expect(postBody).toEqual({
      observed_evidence: ["Evidencia uno", "Evidencia dos"],
      gaps: ["Brecha uno"],
      follow_up_needed: true,
      notes: "Nota sintética",
    });
    const text = document.body.textContent ?? "";
    expect(text).toContain(REQUIREMENT_ID);
    expect(text).toContain(INTERVIEWER_ID);
    expect(text).toContain(CREATED_AT);
    const feedbackTable = screen.getByRole("table", { name: "Historial de feedback" });
    expect(feedbackTable.parentElement?.className).toContain("overflow-x-auto");
    expect(screen.queryByLabelText(/score|puntuación|decisión/i)).toBeNull();
  });

  it("muestra el 403 del servidor al enviar feedback", async () => {
    mockFetch((url, init) => {
      if (
        url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}/feedback` &&
        init?.method === "POST"
      ) {
        return errorResponse(403, "Rol insuficiente.");
      }
      if (url.pathname === `/api/v1/interviews/questions/${QUESTION_ID}/feedback`) {
        return jsonResponse(makeFeedbackList([]));
      }
      return errorResponse(404, "no encontrado");
    });
    render(<FeedbackForm questionId={QUESTION_ID} requirementId={REQUIREMENT_ID} />);
    fireEvent.submit(screen.getByRole("button", { name: "Registrar feedback" }).closest("form")!);
    expect((await screen.findByRole("alert")).textContent).toContain("403: Rol insuficiente.");
  });
});

describe("GuideHistory", () => {
  it("muestra el historial saneado sin CV ni secretos", async () => {
    mockFetch((url) => {
      if (url.pathname === `${GUIDES_PATH}/${GUIDE_ID}/revisions`) {
        return jsonResponse(
          makeRevisionList({
            review_required: true,
            questions: [{ question: CV_MARKER, requirement_id: REQUIREMENT_ID }],
            rejected_questions: [],
            limitations: [],
            secret: SECRET_MARKER,
          }),
        );
      }
      return errorResponse(404, "no encontrado");
    });

    render(<GuideHistory guideId={GUIDE_ID} />);
    expect(await screen.findByText("v1")).toBeTruthy();
    const historyTable = screen.getByRole("table", { name: "Revisiones de la guía" });
    expect(historyTable.parentElement?.className).toContain("overflow-x-auto");
    expect(screen.getByText(INTERVIEWER_ID)).toBeTruthy();
    expect(screen.getByText(CREATED_AT)).toBeTruthy();
    expect(screen.getByText(/1 preguntas · 0 rechazadas · 0 limitaciones/)).toBeTruthy();
    const text = document.body.textContent ?? "";
    expect(text).not.toContain(CV_MARKER);
    expect(text).not.toContain(SECRET_MARKER);
  });

  it("distingue el historial vacío del error 404", async () => {
    mockFetch(() => jsonResponse({ items: [], total: 0, limit: 50, offset: 0 }));
    render(<GuideHistory guideId={GUIDE_ID} />);
    expect(
      await screen.findByText("Todavía no hay revisiones registradas para esta guía."),
    ).toBeTruthy();
    cleanup();

    mockFetch(() => errorResponse(404, "Guía no encontrada."));
    render(<GuideHistory guideId={GUIDE_ID} />);
    expect((await screen.findByRole("alert")).textContent).toContain("404: Guía no encontrada.");
  });
});
