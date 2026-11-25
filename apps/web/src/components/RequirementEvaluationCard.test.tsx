import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type {
  RequirementEvaluation,
  RequirementEvaluationStatus,
} from "../lib/types";
import { RequirementEvaluationCard } from "./RequirementEvaluationCard";

const STATUSES = [
  ["supported", "Respaldado", "✓"],
  ["partial", "Parcial", "◐"],
  ["not_found", "No encontrado", "∅"],
  ["needs_review", "Requiere revisión", "!"],
] as const;

function makeEvaluation(
  status: RequirementEvaluationStatus,
): RequirementEvaluation {
  return {
    id: "evaluation-1",
    requirement_id: "requirement-1",
    status,
    explanation: "Evaluación sintética.",
    evidence: [],
    limitations: [],
    review_required: false,
    reviewed_by: null,
    reviewed_at: null,
    created_at: "2026-01-01T00:00:00Z",
  };
}

describe("RequirementEvaluationCard", () => {
  afterEach(() => {
    cleanup();
  });

  it("distingue los cuatro estados por etiqueta y marca", () => {
    for (const [status, label, mark] of STATUSES) {
      render(
        <RequirementEvaluationCard
          assessmentId="assessment-1"
          evaluation={makeEvaluation(status)}
        />,
      );

      const badge = document.querySelector(`[data-status="${status}"]`);
      expect(badge?.textContent).toContain(label);
      expect(badge?.querySelector('[aria-hidden="true"]')?.textContent).toBe(mark);
      expect(screen.getByRole("heading", { level: 4 }).textContent).toContain(label);
      cleanup();
    }
  });

  it("explica la ausencia de evidencia verificable", () => {
    render(
      <RequirementEvaluationCard
        assessmentId="assessment-1"
        evaluation={makeEvaluation("not_found")}
      />,
    );

    expect(screen.getByText("Sin evidencia verificable para este requisito.")).toBeTruthy();
  });
});
