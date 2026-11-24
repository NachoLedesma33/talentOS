"use client";

import { useEffect, useState } from "react";
import { DocumentReview } from "../../components/DocumentReview";
import { DocumentUpload } from "../../components/DocumentUpload";
import { ApiError, apiFetch } from "../../lib/api";
import type { CandidateList, Document as DocumentDto } from "../../lib/types";

export default function DocumentsPage() {
  const [candidates, setCandidates] = useState<CandidateList | null>(null);
  const [candidateError, setCandidateError] = useState<string | null>(null);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CandidateList>("/api/v1/candidates?limit=100").then(
      setCandidates,
      (cause: unknown) => {
        setCandidateError(
          cause instanceof ApiError
            ? `${cause.status}: ${cause.message}`
            : "No se pudo cargar la lista de candidatos.",
        );
      },
    );
  }, []);

  function handleUploaded(document: DocumentDto) {
    setSelectedDocumentId(document.id);
  }

  return (
    <div className="space-y-6">
      <section className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Documentos</h1>
        <p className="text-sm text-text-muted">
          Carga de CVs y confirmación humana de campos con evidencia.
        </p>
      </section>

      {candidateError ? (
        <p role="alert" className="text-sm text-text">
          {candidateError}
        </p>
      ) : null}
      <DocumentUpload
        candidates={candidates?.items ?? []}
        onUploaded={handleUploaded}
      />

      {selectedDocumentId ? <DocumentReview documentId={selectedDocumentId} /> : null}
    </div>
  );
}
