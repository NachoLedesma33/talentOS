"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type {
  ActivityList,
  Candidate,
  CandidateList,
  NoteList,
} from "../lib/types";
import { CandidateForm } from "./CandidateForm";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";

const PAGE_SIZE = 20;

type LoadStatus = "loading" | "ready" | "error";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function CandidatesPanel() {
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadedRequestKey, setLoadedRequestKey] = useState<string | null>(null);

  const [notes, setNotes] = useState<NoteList>([]);
  const [notesStatus, setNotesStatus] = useState<LoadStatus>("loading");
  const [notesError, setNotesError] = useState<string | null>(null);
  const [notesLoadedId, setNotesLoadedId] = useState<string | null>(null);

  const [activity, setActivity] = useState<ActivityList>([]);
  const [activityStatus, setActivityStatus] = useState<LoadStatus>("loading");
  const [activityError, setActivityError] = useState<string | null>(null);
  const [activityLoadedId, setActivityLoadedId] = useState<string | null>(null);

  const requestKey = `${appliedQuery}|${offset}|${refreshToken}`;

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (appliedQuery) {
      params.set("q", appliedQuery);
    }

    apiFetch<CandidateList>(`/api/v1/candidates?${params.toString()}`).then(
      (result) => {
        if (!active) {
          return;
        }
        setCandidates(result.items);
        setTotal(result.total);
        setLoadStatus("ready");
        setLoadedRequestKey(requestKey);
        setSelectedId((current) =>
          current && result.items.some((candidate) => candidate.id === current)
            ? current
            : (result.items[0]?.id ?? null),
        );
      },
      (error: unknown) => {
        if (!active) {
          return;
        }
        setCandidates([]);
        setTotal(0);
        setSelectedId(null);
        setLoadStatus("error");
        setLoadError(describeError(error, "No se pudieron cargar los candidatos."));
        setLoadedRequestKey(requestKey);
      },
    );

    return () => {
      active = false;
    };
  }, [appliedQuery, offset, refreshToken, requestKey]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    let active = true;
    apiFetch<NoteList>(`/api/v1/candidates/${selectedId}/notes`).then(
      (items) => {
        if (active) {
          setNotes(items);
          setNotesStatus("ready");
          setNotesLoadedId(selectedId);
        }
      },
      (error: unknown) => {
        if (active) {
          setNotesStatus("error");
          setNotesError(describeError(error, "No se pudieron cargar las notas."));
          setNotesLoadedId(selectedId);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) {
      return;
    }
    let active = true;
    apiFetch<ActivityList>(`/api/v1/candidates/${selectedId}/activity`).then(
      (items) => {
        if (active) {
          setActivity(items);
          setActivityStatus("ready");
          setActivityLoadedId(selectedId);
        }
      },
      (error: unknown) => {
        if (active) {
          setActivityStatus("error");
          setActivityError(describeError(error, "No se pudo cargar la actividad."));
          setActivityLoadedId(selectedId);
        }
      },
    );
    return () => {
      active = false;
    };
  }, [selectedId]);

  const isCurrentRequest = loadedRequestKey === requestKey;
  const visibleLoadStatus: LoadStatus = isCurrentRequest ? loadStatus : "loading";
  const visibleLoadError = isCurrentRequest ? loadError : null;
  const visibleCandidates = isCurrentRequest ? candidates : [];
  const visibleTotal = isCurrentRequest ? total : 0;
  const selectedCandidate =
    visibleCandidates.find((candidate) => candidate.id === selectedId) ?? null;

  const visibleNotesStatus: LoadStatus =
    notesLoadedId === selectedId ? notesStatus : "loading";
  const visibleNotesError = notesLoadedId === selectedId ? notesError : null;
  const visibleNotes = notesLoadedId === selectedId ? notes : [];

  const visibleActivityStatus: LoadStatus =
    activityLoadedId === selectedId ? activityStatus : "loading";
  const visibleActivityError = activityLoadedId === selectedId ? activityError : null;
  const visibleActivity = activityLoadedId === selectedId ? activity : [];

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedQuery(query.trim());
    setOffset(0);
  }

  function handleCreated(candidate: Candidate) {
    setQuery("");
    setAppliedQuery("");
    setOffset(0);
    setSelectedId(candidate.id);
    setRefreshToken((current) => current + 1);
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="candidates-list-heading" className="space-y-3">
        <h2 id="candidates-list-heading" className="text-lg font-semibold">
          Listado de candidatos
        </h2>
        <form onSubmit={handleSearch} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="candidate-search" className="block">
              Búsqueda (nombre o correo)
            </Label>
            <Input
              id="candidate-search"
              type="search"
              value={query}
              maxLength={200}
              onChange={(event) => {
                setQuery(event.target.value);
              }}
            />
          </div>
          <Button type="submit">Buscar</Button>
          <p className="text-sm text-text-muted">Total: {visibleTotal}</p>
        </form>

        <div aria-live="polite">
          {visibleLoadStatus === "loading" ? (
            <p role="status" className="text-sm text-text-muted">
              Cargando candidatos…
            </p>
          ) : null}
          {visibleLoadStatus === "error" ? (
            <p role="alert" className="text-sm text-text">
              {visibleLoadError}
            </p>
          ) : null}
          {visibleLoadStatus === "ready" && visibleCandidates.length === 0 ? (
            <p className="text-sm text-text-muted">No hay candidatos para esta búsqueda.</p>
          ) : null}
        </div>

        {visibleLoadStatus === "ready" && visibleCandidates.length > 0 ? (
          <ul className="space-y-2">
            {visibleCandidates.map((candidate) => (
              <li key={candidate.id}>
                <Card className="flex flex-wrap items-center justify-between gap-3 p-3">
                  <div className="space-y-0">
                    <p className="text-sm font-semibold">{candidate.name}</p>
                    <p className="text-xs text-text-muted">
                      {candidate.email}
                      {candidate.location ? ` · ${candidate.location}` : ""}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant={candidate.id === selectedId ? "secondary" : "outline"}
                    size="sm"
                    aria-label={`Ver detalle de ${candidate.name}`}
                    aria-pressed={candidate.id === selectedId}
                    onClick={() => {
                      setSelectedId(candidate.id);
                    }}
                  >
                    Ver detalle
                  </Button>
                </Card>
              </li>
            ))}
          </ul>
        ) : null}

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOffset((current) => Math.max(0, current - PAGE_SIZE));
            }}
            disabled={offset === 0}
          >
            Anterior
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOffset((current) => current + PAGE_SIZE);
            }}
            disabled={visibleLoadStatus !== "ready" || offset + PAGE_SIZE >= visibleTotal}
          >
            Siguiente
          </Button>
          <span className="text-sm text-text-muted">
            {visibleLoadStatus === "ready"
              ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, visibleTotal)}`
              : "—"}
          </span>
        </div>
      </section>

      <section aria-labelledby="candidate-detail-heading" className="space-y-3">
        <h2 id="candidate-detail-heading" className="text-lg font-semibold">
          Detalle del candidato
        </h2>
        {selectedCandidate ? (
          <Card className="space-y-1 p-3">
            <p className="text-sm font-semibold">{selectedCandidate.name}</p>
            <p className="text-sm text-text-muted">{selectedCandidate.email}</p>
            <p className="text-sm text-text-muted">
              {selectedCandidate.location ?? "Sin ubicación"} ·{" "}
              {selectedCandidate.profile_status}
            </p>
          </Card>
        ) : (
          <Card className="p-3 text-sm text-text-muted">
            Selecciona un candidato para ver su detalle.
          </Card>
        )}

        <div className="grid gap-4 md:grid-cols-2">
          <div aria-labelledby="candidate-notes-heading" className="space-y-2">
            <h3 id="candidate-notes-heading" className="text-sm font-semibold">
              Notas internas
            </h3>
            <div aria-live="polite">
              {!selectedCandidate ? (
                <p className="text-sm text-text-muted">Sin candidato seleccionado.</p>
              ) : visibleNotesStatus === "loading" ? (
                <p role="status" className="text-sm text-text-muted">
                  Cargando notas…
                </p>
              ) : visibleNotesStatus === "error" ? (
                <p role="alert" className="text-sm text-text">
                  {visibleNotesError}
                </p>
              ) : visibleNotes.length === 0 ? (
                <p className="text-sm text-text-muted">Sin notas registradas.</p>
              ) : (
                <ul className="space-y-1">
                  {visibleNotes.map((note) => (
                    <li key={note.id}>
                      <Card className="p-3 text-sm">
                        {note.body}
                        <span className="block text-xs text-text-muted">
                          Autor: {note.author_id}
                        </span>
                      </Card>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div aria-labelledby="candidate-activity-heading" className="space-y-2">
            <h3 id="candidate-activity-heading" className="text-sm font-semibold">
              Actividad
            </h3>
            <div aria-live="polite">
              {!selectedCandidate ? (
                <p className="text-sm text-text-muted">Sin candidato seleccionado.</p>
              ) : visibleActivityStatus === "loading" ? (
                <p role="status" className="text-sm text-text-muted">
                  Cargando actividad…
                </p>
              ) : visibleActivityStatus === "error" ? (
                <p role="alert" className="text-sm text-text">
                  {visibleActivityError}
                </p>
              ) : visibleActivity.length === 0 ? (
                <p className="text-sm text-text-muted">Sin actividad registrada.</p>
              ) : (
                <ul className="space-y-1">
                  {visibleActivity.map((entry) => (
                    <li key={entry.id}>
                      <Card className="p-3 text-sm">
                        {entry.action} · {entry.resource_type}
                        <span className="block text-xs text-text-muted">{entry.timestamp}</span>
                      </Card>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="candidate-form-heading" className="space-y-3">
        <h2 id="candidate-form-heading" className="text-lg font-semibold">
          Alta de candidato
        </h2>
        <CandidateForm onCreated={handleCreated} />
      </section>
    </div>
  );
}
