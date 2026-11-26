"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  AssessmentComparison as AssessmentComparisonDto,
  AssessmentEvidenceRef,
  AssessmentStatus,
  RequirementEvaluationStatus,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";

const STATUS_LABELS: Record<RequirementEvaluationStatus, string> = {
  supported: "Respaldado",
  partial: "Parcial",
  not_found: "No encontrado",
  needs_review: "Requiere revisión",
};

const ASSESSMENT_STATUS_LABELS: Record<AssessmentStatus, string> = {
  pending: "Pendiente",
  completed: "Completada",
  failed: "Fallida",
  needs_review: "Requiere revisión",
};

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo completar la comparación.";
}

function statusLabel(status: RequirementEvaluationStatus | null): string {
  return status ? STATUS_LABELS[status] : "—";
}

function optionalText(value: string | null): string {
  return value && value.length > 0 ? value : "—";
}

function truncate(text: string, limit = 120): string {
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function evidenceText(refs: AssessmentEvidenceRef[]): string {
  if (refs.length === 0) return "Sin evidencia verificable";
  return refs
    .map((item) =>
      `${item.document_id} · ${item.field_name} · p.${item.page} · «${truncate(item.quote, 80)}»`,
    )
    .join("; ");
}

export function AssessmentComparison() {
  const [baseId, setBaseId] = useState("");
  const [otherId, setOtherId] = useState("");
  const [comparison, setComparison] = useState<AssessmentComparisonDto | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const base = baseId.trim();
    const other = otherId.trim();
    if (!base || !other || loading) return;

    setLoading(true);
    setError(null);
    setComparison(null);
    try {
      const result = await apiFetch<AssessmentComparisonDto>(
        `/api/v1/assessment/${encodeURIComponent(base)}/compare?other_id=${encodeURIComponent(other)}`,
      );
      setComparison(result);
    } catch (cause) {
      setError(describeError(cause));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section aria-labelledby="comparison-heading" aria-busy={loading} className="space-y-3">
      <div className="space-y-1">
        <h2 id="comparison-heading" className="text-lg font-semibold">
          Comparar evaluaciones
        </h2>
        <p className="text-sm text-text-muted">
          Cambios por requisito entre versiones, con modelo y prompt de cada evaluación.
        </p>
      </div>

      <form onSubmit={(event) => void compare(event)} className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1 space-y-1">
          <Label htmlFor="comparison-base-id" className="block">
            Evaluación base
          </Label>
          <Input
            id="comparison-base-id"
            value={baseId}
            onChange={(event) => setBaseId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <div className="min-w-56 flex-1 space-y-1">
          <Label htmlFor="comparison-other-id" className="block">
            Otra evaluación
          </Label>
          <Input
            id="comparison-other-id"
            value={otherId}
            onChange={(event) => setOtherId(event.target.value)}
            required
            placeholder="00000000-0000-4000-8000-000000000000"
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? "Comparando…" : "Comparar evaluaciones"}
        </Button>
      </form>

      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {loading ? "Comparando evaluaciones…" : null}
      </p>
      {error ? (
        <Card role="alert" className="p-3 text-sm">
          {error}
        </Card>
      ) : null}
      {!comparison && !error && !loading ? (
        <p className="text-sm text-text-muted">
          Ingresa dos IDs de evaluación de la misma postulación para ver los cambios.
        </p>
      ) : null}

      {comparison ? (
        <div className="space-y-3">
          <dl className="grid gap-2 text-xs text-text-muted md:grid-cols-2">
            <Card className="p-2">
              <dt className="font-semibold text-text">Evaluación base</dt>
              <dd>
                {comparison.base.assessment_id} · {ASSESSMENT_STATUS_LABELS[comparison.base.status]}
              </dd>
              <dd>Modelo: {comparison.base.model_version}</dd>
              <dd>Prompt: {comparison.base.prompt_version}</dd>
            </Card>
            <Card className="p-2">
              <dt className="font-semibold text-text">Evaluación comparada</dt>
              <dd>
                {comparison.target.assessment_id} · {ASSESSMENT_STATUS_LABELS[comparison.target.status]}
              </dd>
              <dd>Modelo: {comparison.target.model_version}</dd>
              <dd>Prompt: {comparison.target.prompt_version}</dd>
            </Card>
          </dl>

          <Table>
            <TableCaption className="pb-2 text-left text-xs text-text-muted">
              Cambios trazables por requisito, sin puntuación agregada.
            </TableCaption>
            <TableHeader>
              <TableRow className="border-y border-border text-xs uppercase text-text-muted">
                <TableHead scope="col" className="px-2 py-2">Requisito</TableHead>
                <TableHead scope="col" className="px-2 py-2">Estado</TableHead>
                <TableHead scope="col" className="px-2 py-2">Explicación</TableHead>
                <TableHead scope="col" className="px-2 py-2">Evidencia</TableHead>
                <TableHead scope="col" className="px-2 py-2">Revisión</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {comparison.changes.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="px-2 py-3 text-sm text-text-muted">
                    No hay cambios registrados entre estas versiones.
                  </TableCell>
                </TableRow>
              ) : (
                comparison.changes.map((change) => (
                  <TableRow key={change.requirement_id} className="border-b border-border align-top">
                    <TableHead scope="row" className="px-2 py-2 text-xs font-semibold">
                      {change.requirement_id}
                    </TableHead>
                    <TableCell className="px-2 py-2">
                      <p>Antes: {statusLabel(change.status.before)}</p>
                      <p>Después: {statusLabel(change.status.after)}</p>
                      <p className="text-xs text-text-muted">
                        {change.status.changed ? "Estado modificado" : "Sin cambios"}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2">
                      <p>Antes: {optionalText(change.explanation.before)}</p>
                      <p>Después: {optionalText(change.explanation.after)}</p>
                      <p className="text-xs text-text-muted">
                        {change.explanation.changed ? "Explicación modificada" : "Sin cambios"}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2">
                      <p>Antes: {evidenceText(change.evidence_refs.before)}</p>
                      <p>Después: {evidenceText(change.evidence_refs.after)}</p>
                      <p className="text-xs text-text-muted">
                        {change.evidence_refs.changed ? "Evidencia modificada" : "Sin cambios"}
                      </p>
                    </TableCell>
                    <TableCell className="px-2 py-2 text-xs">
                      Antes: {change.review_required.before ? "Sí" : "No"}
                      <br />
                      Después: {change.review_required.after ? "Sí" : "No"}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </section>
  );
}
