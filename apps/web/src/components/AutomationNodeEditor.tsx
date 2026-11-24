"use client";

import { Fragment, useId, useState, type ReactNode } from "react";
import type {
  ApplicationStage,
  AutomationAction,
  AutomationActionPayload,
  AutomationActionType,
  AutomationCondition,
  AutomationConditionField,
  AutomationConditionOperator,
  AutomationTrigger,
  AutomationVersionCreate,
  JobStatus,
} from "../lib/types";

export const MAX_CONDITIONS = 10;
export const MAX_ACTIONS = 10;

export const AUTOMATION_CONDITION_FIELDS: AutomationConditionField[] = [
  "to_stage",
  "from_stage",
  "job_status",
];
export const AUTOMATION_CONDITION_OPERATORS: AutomationConditionOperator[] = ["eq", "neq", "in"];
export const AUTOMATION_ACTION_TYPES: AutomationActionType[] = [
  "create_task",
  "create_message_draft",
  "request_approval",
  "record_note",
  "propose_stage_change",
  "run_authorized_analysis",
];
export const AUTOMATION_STAGE_VALUES: ApplicationStage[] = [
  "applied",
  "screening",
  "interview",
  "offer",
  "hired",
  "rejected",
];
export const AUTOMATION_JOB_STATUS_VALUES: JobStatus[] = [
  "draft",
  "open",
  "paused",
  "closed",
  "archived",
];

export const AUTOMATION_EMPTY_ACTION_PAYLOAD: AutomationActionPayload = {
  template_id: null,
  note: null,
  target_stage: null,
};

const NODE_CARD_CLASS = "h-full w-full rounded-sm border border-border bg-surface p-3";
const SELECT_CLASS = "min-w-0 rounded-sm border border-border bg-surface px-2 py-2 text-sm";
const BUTTON_CLASS =
  "rounded-sm border border-border px-2 py-1 text-sm font-semibold disabled:opacity-60";

export function automationConditionValues(field: AutomationConditionField): string[] {
  return field === "job_status" ? AUTOMATION_JOB_STATUS_VALUES : AUTOMATION_STAGE_VALUES;
}

export function createAutomationCondition(): AutomationCondition {
  return { field: "to_stage", operator: "eq", value: "interview" };
}

export function createAutomationAction(): AutomationAction {
  return { type: "create_task", payload: { ...AUTOMATION_EMPTY_ACTION_PAYLOAD } };
}

export interface AutomationNodeEditorValue {
  trigger: AutomationTrigger;
  conditions: AutomationCondition[];
  actions: AutomationAction[];
}

/** Serializador único del snapshot enviado a POST /versions. Sin campos libres. */
export function buildAutomationVersionPayload(
  value: AutomationNodeEditorValue,
): AutomationVersionCreate {
  return {
    trigger: { event_type: value.trigger.event_type },
    conditions: value.conditions.map((condition) => ({
      field: condition.field,
      operator: condition.operator,
      value: condition.value,
    })),
    actions: value.actions.map((action) => ({
      type: action.type,
      payload: {
        ...AUTOMATION_EMPTY_ACTION_PAYLOAD,
        target_stage:
          action.type === "propose_stage_change" ? action.payload.target_stage : null,
      },
    })),
  };
}

function NodeConnector() {
  return (
    <li
      aria-hidden="true"
      data-testid="automation-node-connector"
      className="flex w-7 shrink-0 items-center justify-center text-text-muted"
    >
      <svg width="28" height="12" viewBox="0 0 28 12" focusable="false" aria-hidden="true">
        <path
          d="M1 6h20m-5-4 5 4-5 4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </li>
  );
}

interface AutomationNodeEditorProps {
  value: AutomationNodeEditorValue;
  onChange: (next: AutomationNodeEditorValue) => void;
  disabled?: boolean;
}

/** Editor controlado: no llama a la API; el servidor sigue siendo la autoridad. */
export function AutomationNodeEditor({
  value,
  onChange,
  disabled = false,
}: AutomationNodeEditorProps) {
  const idBase = useId();
  const [announcement, setAnnouncement] = useState("");

  const emptyConditionValue = value.conditions.some((condition) =>
    Array.isArray(condition.value) ? condition.value.length === 0 : condition.value.length === 0,
  );
  const error = value.actions.length === 0
    ? "Añade al menos una acción antes de guardar."
    : emptyConditionValue
      ? "Selecciona un valor para cada condición."
      : value.actions.some(
            (action) =>
              action.type === "propose_stage_change" && !action.payload.target_stage,
          )
        ? "Selecciona la etapa propuesta de cada acción."
        : null;

  function emit(next: AutomationNodeEditorValue, message: string): void {
    onChange(next);
    setAnnouncement(message);
  }

  function addCondition(): void {
    if (value.conditions.length >= MAX_CONDITIONS) return;
    const count = value.conditions.length + 1;
    emit(
      { ...value, conditions: [...value.conditions, createAutomationCondition()] },
      `Condición añadida. ${count} de ${MAX_CONDITIONS}.`,
    );
  }

  function addAction(): void {
    if (value.actions.length >= MAX_ACTIONS) return;
    const count = value.actions.length + 1;
    emit(
      { ...value, actions: [...value.actions, createAutomationAction()] },
      `Acción añadida. ${count} de ${MAX_ACTIONS}.`,
    );
  }

  function updateCondition(index: number, next: AutomationCondition): void {
    emit(
      {
        ...value,
        conditions: value.conditions.map((item, position) => (position === index ? next : item)),
      },
      `Condición ${index + 1} actualizada.`,
    );
  }

  function updateAction(index: number, next: AutomationAction): void {
    emit(
      {
        ...value,
        actions: value.actions.map((item, position) => (position === index ? next : item)),
      },
      `Acción ${index + 1} actualizada.`,
    );
  }

  function removeCondition(index: number): void {
    emit(
      {
        ...value,
        conditions: value.conditions.filter((_, position) => position !== index),
      },
      `Condición ${index + 1} eliminada.`,
    );
  }

  function removeAction(index: number): void {
    emit(
      {
        ...value,
        actions: value.actions.filter((_, position) => position !== index),
      },
      `Acción ${index + 1} eliminada.`,
    );
  }

  function moveAction(index: number, direction: -1 | 1): void {
    const target = index + direction;
    if (target < 0 || target >= value.actions.length) return;
    const actions = [...value.actions];
    const moved = actions[index];
    actions.splice(index, 1);
    actions.splice(target, 0, moved);
    emit(
      { ...value, actions },
      `Acción ${index + 1} movida ${direction < 0 ? "arriba" : "abajo"}.`,
    );
  }

  const cards: Array<{ key: string; content: ReactNode }> = [
    {
      key: "trigger",
      content: (
        <div role="group" aria-label="Disparador" className={NODE_CARD_CLASS}>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
            Disparador
          </p>
          <div className="mt-2 space-y-1">
            <label
              htmlFor={`${idBase}-trigger`}
              className="block text-sm font-semibold"
            >
              Evento del disparador
            </label>
            <select
              id={`${idBase}-trigger`}
              value={value.trigger.event_type}
              onChange={() => undefined}
              disabled={disabled}
              className={`${SELECT_CLASS} w-full bg-surface-muted`}
            >
              <option value="application.stage_changed">application.stage_changed</option>
            </select>
          </div>
        </div>
      ),
    },
    ...value.conditions.map((condition, index) => {
      const choices = automationConditionValues(condition.field);
      const isList = condition.operator === "in";
      return {
        key: `condition-${index}`,
        content: (
          <div
            role="group"
            aria-label={`Condición ${index + 1} de ${value.conditions.length}`}
            className={NODE_CARD_CLASS}
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
                {`Condición ${index + 1}`}
              </p>
              <button
                type="button"
                aria-label={`Eliminar condición ${index + 1}`}
                onClick={() => removeCondition(index)}
                disabled={disabled}
                className={BUTTON_CLASS}
              >
                Eliminar
              </button>
            </div>
            <div className="mt-2 grid gap-2">
              <div className="space-y-1">
                <label
                  htmlFor={`${idBase}-condition-field-${index}`}
                  className="block text-sm font-semibold"
                >
                  {`Campo ${index + 1}`}
                </label>
                <select
                  id={`${idBase}-condition-field-${index}`}
                  value={condition.field}
                  onChange={(event) => {
                    const field = event.target.value as AutomationConditionField;
                    updateCondition(index, {
                      field,
                      operator: condition.operator,
                      value: automationConditionValues(field)[0],
                    });
                  }}
                  disabled={disabled}
                  className={`${SELECT_CLASS} w-full`}
                >
                  {AUTOMATION_CONDITION_FIELDS.map((field) => (
                    <option key={field} value={field}>
                      {field}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label
                  htmlFor={`${idBase}-condition-operator-${index}`}
                  className="block text-sm font-semibold"
                >
                  {`Operador ${index + 1}`}
                </label>
                <select
                  id={`${idBase}-condition-operator-${index}`}
                  value={condition.operator}
                  onChange={(event) => {
                    const operator = event.target.value as AutomationConditionOperator;
                    updateCondition(index, {
                      ...condition,
                      operator,
                      value: operator === "in" ? [choices[0]] : choices[0],
                    });
                  }}
                  disabled={disabled}
                  className={`${SELECT_CLASS} w-full`}
                >
                  {AUTOMATION_CONDITION_OPERATORS.map((operator) => (
                    <option key={operator} value={operator}>
                      {operator}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <label
                  htmlFor={`${idBase}-condition-value-${index}`}
                  className="block text-sm font-semibold"
                >
                  {`${isList ? "Valores" : "Valor"} ${index + 1}`}
                </label>
                <select
                  id={`${idBase}-condition-value-${index}`}
                  multiple={isList}
                  required
                  value={
                    isList
                      ? Array.isArray(condition.value)
                        ? condition.value
                        : []
                      : typeof condition.value === "string"
                        ? condition.value
                        : ""
                  }
                  onChange={(event) => {
                    const selected = Array.from(event.target.selectedOptions).map(
                      (option) => option.value,
                    );
                    updateCondition(index, {
                      ...condition,
                      value: isList ? selected : (selected[0] ?? choices[0]),
                    });
                  }}
                  disabled={disabled}
                  className={`${SELECT_CLASS} w-full ${isList ? "min-h-20" : ""}`}
                >
                  {choices.map((choice) => (
                    <option key={choice} value={choice}>
                      {choice}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        ),
      };
    }),
    ...value.actions.map((action, index) => ({
      key: `action-${index}`,
      content: (
        <div
          role="group"
          aria-label={`Acción ${index + 1} de ${value.actions.length}`}
          className={NODE_CARD_CLASS}
        >
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">
              {`Acción ${index + 1}`}
            </p>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                aria-label={`Subir acción ${index + 1}`}
                onClick={() => moveAction(index, -1)}
                disabled={disabled || index === 0}
                className={BUTTON_CLASS}
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={`Bajar acción ${index + 1}`}
                onClick={() => moveAction(index, 1)}
                disabled={disabled || index === value.actions.length - 1}
                className={BUTTON_CLASS}
              >
                ↓
              </button>
              <button
                type="button"
                aria-label={`Eliminar acción ${index + 1}`}
                onClick={() => removeAction(index)}
                disabled={disabled}
                className={BUTTON_CLASS}
              >
                Eliminar
              </button>
            </div>
          </div>
          <div className="mt-2 grid gap-2">
            <div className="space-y-1">
              <label
                htmlFor={`${idBase}-action-type-${index}`}
                className="block text-sm font-semibold"
              >
                {`Tipo de acción ${index + 1}`}
              </label>
              <select
                id={`${idBase}-action-type-${index}`}
                value={action.type}
                onChange={(event) => {
                  const type = event.target.value as AutomationActionType;
                  updateAction(index, {
                    type,
                    payload: { ...AUTOMATION_EMPTY_ACTION_PAYLOAD },
                  });
                }}
                disabled={disabled}
                className={`${SELECT_CLASS} w-full`}
              >
                {AUTOMATION_ACTION_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            {action.type === "propose_stage_change" ? (
              <div className="space-y-1">
                <label
                  htmlFor={`${idBase}-action-stage-${index}`}
                  className="block text-sm font-semibold"
                >
                  {`Etapa propuesta ${index + 1}`}
                </label>
                <select
                  id={`${idBase}-action-stage-${index}`}
                  value={action.payload.target_stage ?? ""}
                  onChange={(event) =>
                    updateAction(index, {
                      ...action,
                      payload: {
                        ...action.payload,
                        target_stage: event.target.value as ApplicationStage,
                      },
                    })
                  }
                  required
                  disabled={disabled}
                  className={`${SELECT_CLASS} w-full`}
                >
                  <option value="">Selecciona etapa</option>
                  {AUTOMATION_STAGE_VALUES.map((stage) => (
                    <option key={stage} value={stage}>
                      {stage}
                    </option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
        </div>
      ),
    })),
    {
      key: "result",
      content: (
        <div role="group" aria-label="Resultado" className={NODE_CARD_CLASS}>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Resultado</p>
          <p className="mt-2 text-sm text-text-muted">
            El servidor valida la versión, la ejecuta en modo controlado y registra la traza. Sin
            efectos externos automáticos.
          </p>
        </div>
      ),
    },
  ];

  return (
    <section aria-label="Editor visual de nodos" className="space-y-3">
      <div className="space-y-1">
        <h4 className="text-sm font-semibold">Editor visual</h4>
        <p className="text-sm text-text-muted">
          El orden de los nodos define el snapshot. Sin arrastre: usa subir y bajar para reordenar.
        </p>
      </div>
      <ol
        aria-label="Secuencia de nodos de la automatización"
        className="flex flex-wrap items-stretch gap-2"
      >
        {cards.map((card, index) => (
          <Fragment key={card.key}>
            {index > 0 ? <NodeConnector /> : null}
            <li className="w-80 max-w-full">{card.content}</li>
          </Fragment>
        ))}
      </ol>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-label="Añadir condición"
          onClick={addCondition}
          disabled={disabled || value.conditions.length >= MAX_CONDITIONS}
          className={BUTTON_CLASS}
        >
          Añadir condición
        </button>
        <button
          type="button"
          aria-label="Añadir acción"
          onClick={addAction}
          disabled={disabled || value.actions.length >= MAX_ACTIONS}
          className={BUTTON_CLASS}
        >
          Añadir acción
        </button>
        <span className="self-center text-xs text-text-muted">
          {`Límites: ${MAX_CONDITIONS} condiciones y ${MAX_ACTIONS} acciones.`}
        </span>
      </div>
      {value.conditions.length === 0 ? (
        <p role="note" className="rounded-sm bg-surface-muted p-2 text-sm text-text-muted">
          Sin condiciones: el disparo se evalúa sin filtros adicionales.
        </p>
      ) : null}
      {value.actions.length === 0 ? (
        <p role="note" className="rounded-sm bg-surface-muted p-2 text-sm text-text-muted">
          Sin acciones: añade al menos una antes de guardar.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="rounded-sm border border-border bg-surface-muted p-2 text-sm">
          {error}
        </p>
      ) : null}
      <p role="status" aria-live="polite" className="min-h-5 text-sm text-text-muted">
        {announcement}
      </p>
    </section>
  );
}
