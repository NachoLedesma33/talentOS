"use client";

import { useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { Candidate, Document as DocumentDto } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

type Phase = "idle" | "uploading" | "extracting" | "done" | "error";

const ACCEPTED_TYPES =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function DocumentUpload({
  candidates,
  onUploaded,
}: {
  candidates: Candidate[];
  onUploaded?: (document: DocumentDto) => void;
}) {
  const { t } = useI18n();
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
      setError(describeError(cause, t("document.error")));
      setPhase("error");
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!candidateId || !file) {
      setError(t("document.selectCandidateFile"));
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
    <form onSubmit={handleSubmit} aria-busy={busy}>
      <Card className="space-y-3 p-4">
      <h2 className="text-lg font-semibold">{t("document.title")}</h2>
      <div className="space-y-1">
        <Label htmlFor="document-candidate" className="block">
          {t("document.candidate")}
        </Label>
        {candidates.length > 0 ? (
          <Select
            id="document-candidate"
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            required
            disabled={busy}
          >
            <option value="">{t("document.selectCandidate")}</option>
            {candidates.map((candidate) => (
              <option key={candidate.id} value={candidate.id}>
                {candidate.name}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            id="document-candidate"
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
            placeholder={t("document.candidateUuid")}
            required
            disabled={busy}
          />
        )}
      </div>
      <div className="space-y-1">
        <Label htmlFor="document-file" className="block">
          {t("document.file")}
        </Label>
        <Input
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
          ? t("document.uploading")
          : phase === "extracting"
            ? t("document.extracting")
            : t("document.uploadExtract")}
      </Button>
      <p aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {phase === "done" ? t("document.done") : null}
        {error ? (
          <span role="alert" className="text-text">
            {error}
          </span>
        ) : null}
      </p>
      {phase === "error" && pending ? (
        <Button type="button" variant="secondary" onClick={handleRetry}>
          {t("document.retry")}
        </Button>
      ) : null}
      </Card>
    </form>
  );
}
