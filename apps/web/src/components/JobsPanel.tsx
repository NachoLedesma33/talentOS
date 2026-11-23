"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import type { Job, JobList, JobStatus } from "../lib/types";
import { JobForm } from "./JobForm";
import { RequirementsEditor } from "./RequirementsEditor";

const PAGE_SIZE = 20;

const STATUSES: readonly JobStatus[] = [
  "draft",
  "open",
  "paused",
  "closed",
  "archived",
];

type LoadStatus = "loading" | "ready" | "error" | "forbidden";

function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function JobsPanel() {
  const [statusFilter, setStatusFilter] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadedRequestKey, setLoadedRequestKey] = useState<string | null>(null);

  const requestKey = `${statusFilter}|${offset}|${refreshToken}`;

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (statusFilter) {
      params.set("status", statusFilter);
    }

    apiFetch<JobList>(`/api/v1/jobs?${params.toString()}`).then(
      (result) => {
        if (!active) {
          return;
        }
        setJobs(result.items);
        setTotal(result.total);
        setLoadStatus("ready");
        setLoadedRequestKey(requestKey);
        setSelectedJobId((current) =>
          current && result.items.some((job) => job.id === current)
            ? current
            : (result.items[0]?.id ?? null),
        );
      },
      (error: unknown) => {
        if (!active) {
          return;
        }
        setJobs([]);
        setTotal(0);
        setSelectedJobId(null);
        setLoadStatus(error instanceof ApiError && error.status === 403 ? "forbidden" : "error");
        setLoadError(describeError(error, "No se pudieron cargar las vacantes."));
        setLoadedRequestKey(requestKey);
      },
    );

    return () => {
      active = false;
    };
  }, [statusFilter, offset, refreshToken, requestKey]);

  const isCurrentRequest = loadedRequestKey === requestKey;
  const visibleLoadStatus: LoadStatus = isCurrentRequest ? loadStatus : "loading";
  const visibleLoadError = isCurrentRequest ? loadError : null;
  const visibleJobs = isCurrentRequest ? jobs : [];
  const visibleTotal = isCurrentRequest ? total : 0;
  const selectedJob = visibleJobs.find((job) => job.id === selectedJobId) ?? null;

  function handleCreated(job: Job) {
    setStatusFilter("");
    setOffset(0);
    setSelectedJobId(job.id);
    setRefreshToken((current) => current + 1);
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="jobs-list-heading" className="space-y-3">
        <h2 id="jobs-list-heading" className="text-lg font-semibold">
          Listado de vacantes
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <label htmlFor="jobs-status" className="block text-sm font-semibold">
              Estado
            </label>
            <select
              id="jobs-status"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                setOffset(0);
              }}
              className="rounded-sm border border-border bg-surface px-3 py-2 text-sm"
            >
              <option value="">Todos</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>
          <p className="text-sm text-text-muted">Total: {visibleTotal}</p>
        </div>

        <div aria-live="polite">
          {visibleLoadStatus === "loading" ? (
            <p role="status" className="text-sm text-text-muted">
              Cargando vacantes…
            </p>
          ) : null}
          {visibleLoadStatus === "error" || visibleLoadStatus === "forbidden" ? (
            <p role="alert" className="text-sm text-text">
              {visibleLoadError}
            </p>
          ) : null}
          {visibleLoadStatus === "ready" && visibleJobs.length === 0 ? (
            <p className="text-sm text-text-muted">
              No hay vacantes para este filtro.
            </p>
          ) : null}
        </div>

        {visibleLoadStatus === "ready" && visibleJobs.length > 0 ? (
          <div className="overflow-x-auto rounded-sm border border-border">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Vacantes de la organización activa</caption>
              <thead className="bg-surface-muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Título
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Estado
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Modalidad
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Ubicación
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Responsable
                  </th>
                  <th scope="col" className="px-3 py-2 font-semibold">
                    Acción
                  </th>
                </tr>
              </thead>
              <tbody>
                {visibleJobs.map((job) => (
                  <tr key={job.id} className="border-t border-border">
                    <td className="px-3 py-2 font-semibold">{job.title}</td>
                    <td className="px-3 py-2">{job.status}</td>
                    <td className="px-3 py-2">{job.modality ?? "—"}</td>
                    <td className="px-3 py-2">{job.location ?? "—"}</td>
                    <td className="px-3 py-2" title={job.owner_id}>
                      {job.owner_id.slice(0, 8)}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        aria-label={`Seleccionar vacante ${job.title}`}
                        aria-pressed={job.id === selectedJobId}
                        onClick={() => {
                          setSelectedJobId(job.id);
                        }}
                        className="rounded-sm border border-border px-2 py-1 text-sm font-semibold"
                      >
                        Seleccionar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setOffset((current) => Math.max(0, current - PAGE_SIZE));
            }}
            disabled={offset === 0}
            className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
          >
            Anterior
          </button>
          <button
            type="button"
            onClick={() => {
              setOffset((current) => current + PAGE_SIZE);
            }}
            disabled={visibleLoadStatus !== "ready" || offset + PAGE_SIZE >= visibleTotal}
            className="rounded-sm border border-border px-3 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
          >
            Siguiente
          </button>
          <span className="text-sm text-text-muted">
            {visibleLoadStatus === "ready"
              ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, visibleTotal)}`
              : "—"}
          </span>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-labelledby="job-form-heading" className="space-y-3">
          <h2 id="job-form-heading" className="text-lg font-semibold">
            Alta de vacante
          </h2>
          <JobForm onCreated={handleCreated} />
        </section>
        <RequirementsEditor job={selectedJob} />
      </div>
    </div>
  );
}
