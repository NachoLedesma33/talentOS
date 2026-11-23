---
name: observability-debugging
description: Instrumenta logs, trazas, correlación y métricas de TalentOS sin registrar chain-of-thought ni datos personales, y depura fallos con evidencia reproducible.
---

# Observabilidad y Debugging — TalentOS

## Objetivo

Hacer que cualquier request, tarea en background, webhook o ejecución de agente pueda reconstruirse a partir de identificadores y eventos observables. El diagnóstico debe apoyarse en evidencia verificable, no en suposiciones ni en razonamiento interno del modelo.

## Cuándo activarla

- Instrumentar endpoints, workers, adaptadores, agentes o automatizaciones.
- Depurar errores, timeouts, reintentos, duplicados o resultados de IA inconsistentes.
- Definir métricas de producto o paneles de control.
- Revisar que logs y trazas no contengan secretos, CV completos ni chain-of-thought.
- Investigar un reporte con `correlation_id`.

## Contexto TalentOS

- El SDD 15.1 exige `request_id`, `correlation_id`, `organization_id`, `agent_run_id`, workflow y versión, modelo y versión, duración, estado, herramientas invocadas, reintentos, tokens/costo informados por el proveedor y tipo de error.
- El SDD 15.1 prohíbe registrar chain-of-thought e información personal innecesaria; `AGENTS.md` refuerza: logs sin tokens, contraseñas, CV completos ni datos sensibles.
- `apps/api/app/observability/` es el destino previsto para la instrumentación; los workers y agentes deben propagar el mismo contexto.
- Las métricas de producto del SDD 15.2 incluyen tiempo de procesamiento, exactitud por campo, citas verificadas, fallos por proveedor y acciones aprobadas/rechazadas; cada una necesita definición y forma de cálculo.
- `docs/DEVELOPMENT_WORKFLOW.md` exige evidencia real para `DONE`; un log o traza es evidencia solo si permite reconstruir el caso.

## Procedimiento

1. Leer `TalentOS_SDD.md` secciones 11, 15 y 25, `AGENTS.md`, `TalentOS_ROADMAP.md` sección 3 y `docs/DEVELOPMENT_WORKFLOW.md`.
2. Identificar el límite de ejecución: request HTTP, mensaje de webhook, tarea Celery, nodo LangGraph o entrega a proveedor.
3. Propagar `request_id` y `correlation_id` desde la request hasta worker, adaptador y agente. El `organization_id` se toma del contexto autenticado.
4. Emitir logs estructurados en JSON con campos del SDD 15.1, timestamp UTC, nivel y tipo de error; usar enums y UUIDs, no texto libre para identificadores.
5. Registrar invocaciones de herramientas con nombre, versión, parámetros redactados, resultado resumido y duración; nunca el prompt completo con PII ni el razonamiento paso a paso.
6. En agentes, adjuntar `agent_run_id`, versión de workflow, modelo, versión de prompt, reintentos y consumo informado; marcar salidas validadas/rechazadas y aprobación humana cuando aplique.
7. Para métricas, documentar nombre, unidad, evento que la alimenta y fórmula; “ahorro de tiempo” debe explicar cómo se calcula (SDD 15.2).
8. Depurar en este orden: reproducir con fixture sintética → localizar por `correlation_id` → acotar capa (API, auth, DB, worker, proveedor, agente) → corregir causa → agregar test de regresión → retirar instrumentación temporal sensible.
9. Dejar estado visible al usuario y registro de reintento manual para tareas fallidas; no borrar la traza del fallo.
10. Registrar comandos, salida y resultados observados en el registro de progreso del roadmap según `docs/DEVELOPMENT_WORKFLOW.md`.

## Convenciones

- Logs JSON de una línea por evento; claves estables (`request_id`, `correlation_id`, `organization_id`, `agent_run_id`).
- Errores con categoría y código consistentes; el mensaje al cliente no expone stack, query ni secreto.
- Una ejecución = un `correlation_id` compartido por todos sus eventos, incluido el webhook entrante y la respuesta al proveedor.
- Evidencia = fragmento verificable del documento o evento con ID; observación = dato medido. No registrar interpretación interna como dato.
- Datos de prueba sintéticos; entornos `test` y `staging` sin CV reales.
- Redactar por defecto campos de token, secreto, correo, teléfono y texto de CV; permitir solo IDs y hashes.
- Toda métrica nueva se documenta en el mismo cambio que la implementa.

## Anti-patrones

- Volcar `request.body`, variables de entorno, prompt completo o respuesta cruda del LLM en logs.
- Guardar chain-of-thought, “pensamientos” del agente o instrucciones internas como telemetría.
- Usar logs como base de datos de negocio o fiarse de un mensaje suelto sin `correlation_id`.
- Medir latencia promedio sin definir evento de inicio/fin ni excluir retries; reportar ahorro sin fórmula.
- Repetir la ejecución en producción “a ver si pasa” sin fixture ni hipótesis.
- Desactivar logs de error o aumentar el nivel de log para ocultar fallos.
- Mezclar organizaciones en una sola traza sin `organization_id` verificable.

## Validación

- Ejecutar según el cambio `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app` y `cd apps/api && python -m pytest -q`; frontend `cd apps/web && npx tsc --noEmit` y `cd apps/web && npm run lint` cuando aplique.
- Test de propagación: request → worker → agente → webhook conservan el mismo `correlation_id`.
- Test de esquema de log: todos los eventos obligatorios presentes y tipos correctos.
- Test de redacción: inyectar token, contraseña, correo y fragmento de CV sintético y verificar que no aparecen en logs ni trazas.
- Test de fallo: timeout del proveedor, reintento y error final son diagnosticables por ID y categoría.
- Confirmar que las métricas nuevas tienen definición, unidad y fórmula documentadas.
- En Fase 0, donde `apps/api` aún no existe, la validación es la relectura de este archivo y el chequeo de rutas citadas.

## Checklist

- [ ] Contexto propagado en request, worker y agente.
- [ ] Campos obligatorios del SDD 15.1 presentes en logs/trazas.
- [ ] Sin chain-of-thought, PII, tokens ni CV en telemetría.
- [ ] Errores categorizados y visibles para el usuario.
- [ ] Métricas con unidad, evento y fórmula documentadas.
- [ ] Reproducción sintética y test de regresión agregados.
- [ ] Evidencia de comandos y resultado registrada en el roadmap.

## Referencias

- `TalentOS_SDD.md` secciones 11.2, 15, 16.2 y 25.
- `TalentOS_ROADMAP.md` sección 3 y `docs/DEVELOPMENT_WORKFLOW.md` secciones “Checks” y “Evidencia obligatoria para DONE”.
- `AGENTS.md`, `docs/ENVIRONMENTS.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: FastAPI <https://fastapi.tiangolo.com/>, LangGraph <https://docs.langchain.com/oss/python/langgraph/overview>, PostgreSQL <https://www.postgresql.org/docs/>.
