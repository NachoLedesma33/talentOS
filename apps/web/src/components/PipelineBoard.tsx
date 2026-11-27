"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../lib/api";
import { useI18n, type MessageKey } from "../lib/i18n";
import type {
  Application,
  ApplicationList,
  ApplicationStage,
  StageChange,
  StageChangeRequest,
} from "../lib/types";
import { Button } from "./ui/shadcn/button";
import { Card } from "./ui/shadcn/card";
import { Input } from "./ui/shadcn/input";
import { Label } from "./ui/shadcn/label";
import { Select } from "./ui/shadcn/select";

const PAGE_SIZE = 20;

const STAGES: readonly ApplicationStage[] = [
  "applied",
  "screening",
  "interview",
  "offer",
  "hired",
  "rejected",
];

type LoadStatus = "loading" | "ready" | "error";
type ActionStatus = "idle" | "loading" | "success" | "forbidden" | "error";

function describeError(
  error: unknown,
  fallback: string,
  t: (key: MessageKey) => string,
): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return `${t("pipeline.conflict")}${error.message}`;
    }
    if (error.status === 403) {
      return `${t("pipeline.forbidden")}${error.message}`;
    }
    return `${error.status}: ${error.message}`;
  }
  return fallback;
}

export function PipelineBoard() {
  const { t } = useI18n();
  const [jobFilter, setJobFilter] = useState("");
  const [stageFilter, setStageFilter] = useState("");
  const [appliedJobId, setAppliedJobId] = useState("");
  const [appliedStage, setAppliedStage] = useState("");
  const [offset, setOffset] = useState(0);
  const [refreshToken, setRefreshToken] = useState(0);
  const [applications, setApplications] = useState<Application[]>([]);
  const [total, setTotal] = useState(0);
  const [loadStatus, setLoadStatus] = useState<LoadStatus>("loading");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadedRequestKey, setLoadedRequestKey] = useState<string | null>(null);

  const requestKey = `${appliedJobId}|${appliedStage}|${offset}|${refreshToken}`;

  const [targets, setTargets] = useState<Record<string, ApplicationStage>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [actionStatus, setActionStatus] = useState<ActionStatus>("idle");
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (appliedJobId) {
      params.set("job_id", appliedJobId);
    }
    if (appliedStage) {
      params.set("stage", appliedStage);
    }

    apiFetch<ApplicationList>(`/api/v1/applications?${params.toString()}`).then(
      (result) => {
        if (!active) {
          return;
        }
        setApplications(result.items);
        setTotal(result.total);
        setLoadStatus("ready");
        setLoadedRequestKey(requestKey);
      },
      (error: unknown) => {
        if (!active) {
          return;
        }
        setApplications([]);
        setTotal(0);
        setLoadStatus("error");
        setLoadError(describeError(error, t("pipeline.loadError"), t));
        setLoadedRequestKey(requestKey);
      },
    );

    return () => {
      active = false;
    };
  }, [appliedJobId, appliedStage, offset, refreshToken, requestKey, t]);

  const isCurrentRequest = loadedRequestKey === requestKey;
  const visibleLoadStatus: LoadStatus = isCurrentRequest ? loadStatus : "loading";
  const visibleLoadError = isCurrentRequest ? loadError : null;
  const visibleApplications = isCurrentRequest ? applications : [];
  const visibleTotal = isCurrentRequest ? total : 0;

  function handleFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedJobId(jobFilter.trim());
    setAppliedStage(stageFilter);
    setOffset(0);
  }

  async function handleStageChange(application: Application) {
    const note = (notes[application.id] ?? "").trim();
    const payload: StageChangeRequest = {
      to_stage: targets[application.id] ?? application.stage,
    };
    if (note) {
      payload.note = note;
    }

    setBusyId(application.id);
    setActionStatus("loading");
    setActionMessage(null);
    try {
      const change = await apiFetch<StageChange>(
        `/api/v1/applications/${application.id}/stage`,
        { method: "POST", body: JSON.stringify(payload) },
      );
      setActionStatus("success");
      setActionMessage(`${t("pipeline.updated")}${change.to_stage}.`);
      setRefreshToken((current) => current + 1);
    } catch (error) {
      setActionStatus(error instanceof ApiError && error.status === 403 ? "forbidden" : "error");
      setActionMessage(describeError(error, t("pipeline.changeError"), t));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="pipeline-filters-heading" className="space-y-3">
        <h2 id="pipeline-filters-heading" className="text-lg font-semibold">
          {t("pipeline.filtersTitle")}
        </h2>
        <form onSubmit={handleFilters} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="pipeline-job-filter" className="block">
              {t("pipeline.jobFilter")}
            </Label>
            <Input
              id="pipeline-job-filter"
              type="text"
              value={jobFilter}
              onChange={(event) => {
                setJobFilter(event.target.value);
              }}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pipeline-stage-filter" className="block">
              {t("pipeline.stageFilter")}
            </Label>
            <Select
              id="pipeline-stage-filter"
              value={stageFilter}
              onChange={(event) => {
                setStageFilter(event.target.value);
              }}
            >
              <option value="">{t("pipeline.all")}</option>
              {STAGES.map((stage) => (
                <option key={stage} value={stage}>
                  {stage}
                </option>
              ))}
            </Select>
          </div>
          <Button type="submit">{t("pipeline.apply")}</Button>
          <p className="text-sm text-text-muted">
            {t("pipeline.total")}
            {visibleTotal}
          </p>
        </form>

        <div className="flex items-center gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOffset((current) => Math.max(0, current - PAGE_SIZE));
            }}
            disabled={offset === 0}
          >
            {t("pipeline.previous")}
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              setOffset((current) => current + PAGE_SIZE);
            }}
            disabled={visibleLoadStatus !== "ready" || offset + PAGE_SIZE >= visibleTotal}
          >
            {t("pipeline.next")}
          </Button>
        </div>

        <div aria-live="polite">
          {visibleLoadStatus === "loading" ? (
            <p role="status" className="text-sm text-text-muted">
              {t("pipeline.loading")}
            </p>
          ) : null}
          {visibleLoadStatus === "error" ? (
            <p role="alert" className="text-sm text-text">
              {visibleLoadError}
            </p>
          ) : null}
          {visibleLoadStatus === "ready" && visibleApplications.length === 0 ? (
            <p className="text-sm text-text-muted">{t("pipeline.empty")}</p>
          ) : null}
          <p
            role={
              actionStatus === "error" || actionStatus === "forbidden"
                ? "alert"
                : actionStatus === "success"
                  ? "status"
                  : undefined
            }
            className="min-h-5 text-sm text-text"
          >
            {actionStatus === "loading" ? t("pipeline.changing") : actionMessage}
          </p>
        </div>
      </section>

      <section aria-labelledby="pipeline-board-heading" aria-busy={busyId !== null} className="space-y-3">
        <h2 id="pipeline-board-heading" className="text-lg font-semibold">
          {t("pipeline.boardTitle")}
        </h2>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {STAGES.map((stage) => {
            const columnItems = visibleApplications.filter(
              (application) => application.stage === stage,
            );
            return (
              <section
                key={stage}
                aria-label={`${t("pipeline.stageAria")}${stage}`}
                className="space-y-2"
              >
                <Card className="space-y-2 bg-secondary p-3">
                  <h3 className="text-sm font-semibold">
                    {stage}
                    <span className="ml-2 text-xs text-text-muted">({columnItems.length})</span>
                  </h3>
                  {columnItems.length === 0 ? (
                    <p className="text-sm text-text-muted">{t("pipeline.noApplications")}</p>
                  ) : null}
                  {columnItems.map((application) => (
                    <Card role="article" key={application.id} className="space-y-2 p-3">
                    <p className="text-sm font-semibold" title={application.id}>
                      {t("pipeline.applicationPrefix")}
                      {application.id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-text-muted" title={application.candidate_id}>
                      {t("pipeline.candidateLabel")}
                      {application.candidate_id.slice(0, 8)}
                    </p>
                    <p className="text-xs text-text-muted" title={application.job_id}>
                      {t("pipeline.jobLabel")}
                      {application.job_id.slice(0, 8)}
                    </p>
                    <div className="space-y-1">
                      <Label
                        htmlFor={`stage-target-${application.id}`}
                        className="block text-xs"
                      >
                        {t("pipeline.targetLabel")}
                      </Label>
                      <Select
                        id={`stage-target-${application.id}`}
                        aria-label={`${t("pipeline.targetAria")}${application.id}`}
                        value={targets[application.id] ?? application.stage}
                        onChange={(event) => {
                          const next = event.target.value as ApplicationStage;
                          setTargets((current) => ({ ...current, [application.id]: next }));
                        }}
                        disabled={busyId === application.id}
                      >
                        {STAGES.map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </Select>
                    </div>
                    <div className="space-y-1">
                      <Label
                        htmlFor={`stage-note-${application.id}`}
                        className="block text-xs"
                      >
                        {t("pipeline.noteLabel")}
                      </Label>
                      <Input
                        id={`stage-note-${application.id}`}
                        type="text"
                        maxLength={1000}
                        aria-label={`${t("pipeline.noteAria")}${application.id}`}
                        value={notes[application.id] ?? ""}
                        onChange={(event) => {
                          const next = event.target.value;
                          setNotes((current) => ({ ...current, [application.id]: next }));
                        }}
                        disabled={busyId === application.id}
                      />
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      aria-label={`${t("pipeline.advanceAria")}${application.id}`}
                      onClick={() => {
                        void handleStageChange(application);
                      }}
                      disabled={busyId !== null}
                    >
                      {busyId === application.id
                        ? t("pipeline.advancing")
                        : t("pipeline.advance")}
                    </Button>
                    </Card>
                  ))}
                </Card>
              </section>
            );
          })}
        </div>
      </section>
    </div>
  );
}
