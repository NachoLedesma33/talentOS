"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Candidate, Document as DocumentDto } from "../lib/types";
import { Button } from "./ui/Button";

type Phase = "idle" | "uploading" | "extracting" | "done" | "error";

const ACCEPTED_TYPES =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return "No se pudo completar la carga del documento.";
}

export function DocumentUpload({
  candidates,
  onUploaded,
}: {
  candidates: Candidate[];
  onUploaded?: (document: DocumentDto) => void;
}) {
  const [candidateId, setCandidateId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ candidateId: string; file: File } | null>(null);

  async function run(candidateIdentifier: string, selectedFile: File) {
    setPhase("uploading");
    setError(null);
    const body = new FormData();
    body.append("candidate_id", candidateIdentifier);
    body.append("file", selectedFile);
    try {
      const document = await apiFetch<DocumentDto>("/api/v1/documents/upload", {
        method: "POST",
        body,
      });
      setPhase("extracting");
      await apiFetch(`/api/v1/documents/${document.id}/extract`, { method: "POST" });
      setPhase("done");
      setFile(null);
      onUploaded?.(document);
    } catch (cause) {
      setError(describeError(cause));
      setPhase("error");
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidateId || !file) {
      setError("Selecciona un candidato y un archivo PDF o DOCX.");
      setPhase("error");
      return;
    }
    setPending({ candidateId, file });
    void run(candidateId, file);
  }

  function handleRetry() {
    if (pending) {
      void run(pending.candidateId, pending.file);
    }
  }

  const busy = phase === "uploading" || phase === "extracting";

  return (
    <form onSubmit={handleSubmit} aria-busy={busy} className="space-y-3">
      <h2 className="text-lg font-semibold">Subir CV</h2>
      <div className="space-y-1">
        <label htmlFor="document-candidate" className="block text-sm font-semibold">
          Candidato
        </label>
        {candidates.length > 0 ? (
          <select
            id="document-candidate"
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            required
            disabled={busy}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          >
            <option value="">Selecciona un candidato</option>
            {candidates.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.name}
              </option>
            ))}
          </select>
        ) : (
          <input
            id="document-candidate"
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            placeholder="UUID del candidato"
            required
            disabled={busy}
            className="w-full rounded-sm border border-border bg-surface px-3 py-2 text-sm"
          />
        )}
      </div>
      <div className="space-y-1">
        <label htmlFor="document-file" className="block text-sm font-semibold">
          Archivo PDF o DOCX
        </label>
        <input
          id="document-file"
          type="file"
          accept={ACCEPTED_TYPES}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          required
          disabled={busy}
          className="w-full text-sm"
        />
      </div>
      <Button type="submit" disabled={busy}>
        {phase === "uploading"
          ? "Subiendo…"
          : phase === "extracting"
            ? "Extrayendo…"
            : "Subir y extraer"}
      </Button>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {phase === "done" ? "Documento cargado; extracción solicitada." : null}
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : null}
      </p>
      {phase === "error" && pending ? (
        <Button type="button" variant="secondary" onClick={handleRetry}>
          Reintentar
        </Button>
      ) : null}
    </form>
  );
}
