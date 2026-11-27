"use client";

import { useEffect, useState } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n } from "../lib/i18n";
import type { Job, JobList, JobStatus } from "../lib/types";
import { Button } from "./ui/shadcn/button";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "./ui/shadcn/table";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";
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
  const { t } = useI18n();
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
        setLoadError(describeError(error, t("jobs.loadError")));
        setLoadedRequestKey(requestKey);
      },
    );

    return () => {
      active = false;
    };
  }, [statusFilter, offset, refreshToken, requestKey, t]);

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
          {t("jobs.title")}
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="jobs-status" className="block">
              {t("jobs.filter.status")}
            </Label>
            <Select
              id="jobs-status"
              value={statusFilter}
              onChange={(event) => {
                setStatusFilter(event.target.value);
                setOffset(0);
              }}
            >
              <option value="">{t("jobs.filter.all")}</option>
              {STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </Select>
          </div>
          <p className="text-sm text-text-muted">
            {t("jobs.total")} {visibleTotal}
          </p>
        </div>

        <div aria-live="polite">
          {visibleLoadStatus === "loading" ? (
            <p role="status" className="text-sm text-text-muted">
              {t("jobs.loading")}
            </p>
          ) : null}
          {visibleLoadStatus === "error" || visibleLoadStatus === "forbidden" ? (
            <p role="alert" className="text-sm text-text">
              {visibleLoadError}
            </p>
          ) : null}
          {visibleLoadStatus === "ready" && visibleJobs.length === 0 ? (
            <p className="text-sm text-text-muted">{t("jobs.empty")}</p>
          ) : null}
        </div>

        {visibleLoadStatus === "ready" && visibleJobs.length > 0 ? (
          <Table className="text-left">
            <TableCaption className="sr-only">{t("jobs.caption")}</TableCaption>
            <TableHeader className="bg-surface-muted">
              <TableRow>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.title")}
                </TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.status")}
                </TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.modality")}
                </TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.location")}
                </TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.owner")}
                </TableHead>
                <TableHead scope="col" className="px-3 py-2 font-semibold">
                  {t("jobs.col.action")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {visibleJobs.map((job) => (
                <TableRow key={job.id} className="border-t border-border">
                  <TableCell className="px-3 py-2 font-semibold">{job.title}</TableCell>
                  <TableCell className="px-3 py-2">{job.status}</TableCell>
                  <TableCell className="px-3 py-2">{job.modality ?? "—"}</TableCell>
                  <TableCell className="px-3 py-2">{job.location ?? "—"}</TableCell>
                  <TableCell className="px-3 py-2" title={job.owner_id}>
                    {job.owner_id.slice(0, 8)}
                  </TableCell>
                  <TableCell className="px-3 py-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      aria-label={`${t("jobs.selectAria")} ${job.title}`}
                      aria-pressed={job.id === selectedJobId}
                      onClick={() => {
                        setSelectedJobId(job.id);
                      }}
                    >
                      {t("jobs.select")}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
            {t("jobs.previous")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOffset((current) => current + PAGE_SIZE);
            }}
            disabled={visibleLoadStatus !== "ready" || offset + PAGE_SIZE >= visibleTotal}
          >
            {t("jobs.next")}
          </Button>
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
            {t("jobs.form.title")}
          </h2>
          <JobForm onCreated={handleCreated} />
        </section>
        <RequirementsEditor job={selectedJob} />
      </div>
    </div>
  );
}
