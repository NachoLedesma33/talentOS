---
name: langgraph-workflows
description: Diseña flujos LangGraph de TalentOS con estado tipado, nodos acotados, branching por evidencia, checkpointing por organización e interrupciones reales para aprobación humana.
---

# LangGraph Workflows — TalentOS

## Objetivo
Implementar los flujos multiagente de TalentOS como grafos explícitos, inspeccionables y reanudables. El estado debe hacer visibles las evidencias, las aprobaciones pendientes y los errores; ningún nodo puede saltarse la autorización ni la revisión humana.

## Cuándo activarla
- Al crear o modificar un `StateGraph`, sus nodos, conditional edges, checkpoints o interrupciones en `apps/api/app/agents/`.
- Al implementar el `Recruitment Orchestrator` o la coordinación entre `CV Analyst`, `Job Analyst`, `Matching Analyst`, `Interview Assistant`, `Workflow Assistant` y `Quality Auditor` (SDD §9.2).
- Al modelar estados de ejecución `pending → running → waiting_approval → completed` con `failed`, `cancelled` y `timed_out` (SDD §8.3).
- Al añadir reintentos, timeouts, auditoría de eventos o reanudación de una ejecución.
- No activar para prompts individuales sin grafo ni para reglas deterministas de dominio: usar `ai-agent-engineering` o `python-fastapi`.

## Contexto TalentOS
- LangGraph es la tecnología elegida para flujos con estado, branching y aprobación humana (SDD §6.2, ADR-006).
- Objetivo de observabilidad (SDD Fase 4 / §21): una ejecución se puede inspeccionar, pausar, reanudar y diagnosticar.
- Entidades de persistencia: `AgentRun` con `workflow`, `status`, `input_ref`, `output_ref`; `AgentEvent` con `event_type`, `payload`, `created_at`; `Approval` con `action_type`, `payload`, `status`, `decided_by` (SDD §8.1).
- Flujo de matching del SDD §9.4: solicitud autorizada → vacante/versión → perfil y documentos confirmados → contexto mínimo → evaluación por requisito → validación JSON/referencias → suficiencia de evidencia → revisión humana → guardado y auditoría.
- Estado de cada criterio: `supported`, `partial`, `not_found`, `needs_review` con `evidence_refs` verificables (SDD §9.5).
- Herramientas disponibles solo desde nodos autorizados y a través del tool registry del SDD §10; nunca SQL libre, shell ni filesystem arbitrario.
- Multi-tenancy: `organization_id`, `actor_id`, `correlation_id` y `idempotency_key` forman parte del estado y del thread de checkpoint; otra organización no puede reanudar ni leer la ejecución.
- Human-in-the-loop: `interrupt()` antes de acciones externas o decisiones sensibles; reanudación solo con decisión persistida de usuario autorizado.
- Modo mock: ejecución completa con `LLM_PROVIDER=mock` y datasets sintéticos; el grafo no cambia al cambiar de proveedor.
- Secretos y datos personales: no guardar API keys en estado/checkpoints; minimizar fragmentos de CV y nunca registrar chain-of-thought.

## Procedimiento
1. Leer `TalentOS_SDD.md` §8.3, §9.2, §9.4, §9.5, §10 y §11; leer `AGENTS.md`, `docs/decisions/` y la fase activa de `TalentOS_ROADMAP.md`.
2. Dibujar el grafo en papel antes de codificar: nodos, entrada/salida de cada uno, conditional edges, puntos de `interrupt()` y estados terminales.
3. Definir el estado con TypedDict/Pydantic: `organization_id`, `actor_id`, `correlation_id`, `job_version_id`, `application_id`, `criteria`, `evidence_refs`, `approvals`, `errors`, `status`, `idempotency_key`.
4. Crear nodos pequeños con responsabilidad única; cada nodo valida entrada/salida y llama a servicios de dominio o tools registradas, nunca a repositorios directamente.
5. Implementar branching determinista: si faltan evidencias o hay contradicciones, enrutar a `needs_review` / `Quality Auditor` / aprobación; no confiar en que el modelo “decida” que ya está bien.
6. Configurar checkpointer con claves que incluyan organización y run ID; verificar que un `thread_id` de otra organización no pueda reanudar la ejecución.
7. Insertar `interrupt()` antes de acciones externas, envío de borradores o decisiones de selección; la reanudación consume una decisión de `Approval` ya persistida y verificada.
8. Registrar `AgentEvent` por transición relevante con `correlation_id`, sin payload sensible; actualizar `AgentRun.status` con los enums del SDD.
9. Definir timeouts por nodo, reintentos con límite, dead-letter o estado `failed`, y estrategia de idempotencia para no duplicar borradores ni aprobaciones.
10. Probar el grafo con proveedor mock: ruta con evidencia suficiente, ruta `needs_review`, aprobación rechazada, reanudación, error de tool y acceso cross-tenant.
11. Ejecutar gates de backend, adjuntar evidencia (incluido el timeline observado) y actualizar documentación/ADRs si cambia el contrato del estado.

## Convenciones
- Estado explícito y serializable; nada de objetos ORM ni clientes de proveedor dentro del checkpoint.
- Un nodo = una responsabilidad; el orquestador decide orden y branching, no reemplaza reglas de negocio del dominio.
- Conditional edges usan campos validados del estado (`status`, `review_required`, `evidence_refs`), no texto libre del LLM.
- Checkpointing por ejecución con `organization_id` en la clave; aplicar retención documentada y purgar datos sintéticos de demo sin afectar datos reales.
- HITL real: `interrupt()` + `Approval` + decisión humana; jamás reanudar automáticamente ni simular aprobación en producción.
- Evidencia verificable: cada `evidence_refs` se valida contra documento confirmado, candidato y organización antes de pasar a explicación.
- Tools con argumentos Pydantic, permisos, timeout, rate limit e idempotency key; lectura, borrador y ejecución separadas.
- Modo mock en `local`/`test`: nodos deterministas y fixtures sintéticas; el grafo es idéntico al de un proveedor real.
- Secretos fuera del estado y de logs; datos personales minimizados y sintéticos en pruebas.
- Errores visibles en `AgentRun`/`AgentEvent` con mensaje accionable, sin exponer stack traces ni CV al cliente.

## Anti-patrones
- Grafo con un nodo “haz todo” o branching basado en que el LLM diga “ya está completo”.
- Reanudar un checkpoint sin verificar organización, rol y decisión humana persistida.
- Simular aprobación con un flag en el estado o autoaprobar para que la demo termine rápido.
- Guardar objetos ORM, API keys, tokens, CV completo o chain-of-thought en el checkpoint.
- Compartir `thread_id` entre organizaciones o entre ejecuciones distintas.
- Ejecutar tools de escritura sin idempotency key: duplicar borradores, correos o aprobaciones.
- Aceptar evidencia de otro candidato/documento o de otra organización como `supported`.
- Repetir reintentos sin límite ni estado `failed`/`timed_out`; ocultar errores para mantener “éxito”.
- Crear nodos o paquetes genéricos “para futuros agentes” sin caso de uso en el roadmap.

## Validación
- Ruta exitosa con mock: evidencia suficiente → explicación estructurada → `completed` → `AuditLog`.
- Ruta sin evidencia: `needs_review` → `waiting_approval` → decisión humana → reanudación correcta.
- Aprobación rechazada: no se ejecuta la acción externa; `Approval.status` y `AgentRun.status` coherentes.
- Cross-tenant: `thread_id`/run ID de otra organización → rechazo; tool con ID ajeno → rechazo sin lectura.
- Reintentos: misma idempotency key no duplica efectos; fallo persistente termina en `failed`/`timed_out` con evento visible.
- Inspección: timeline de nodos, tools, duraciones y errores disponible en `AgentEvent` sin secretos ni datos personales.
- Modo mock: suite completa con `LLM_PROVIDER=mock` y datos sintéticos; ningún test usa proveedor pago.
- Gates: `cd apps/api && python -m pytest -q`, `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`.
- En Fase 0 no hay grafos: validar por relectura de SDD, `AGENTS.md` y ADR-006; no instalar LangGraph ni crear nodos vacíos.

## Checklist
- [ ] Grafo dibujado con nodos, edges, interrupciones y estados terminales.
- [ ] Estado tipado con organización, actor, correlación, idempotencia y evidencias.
- [ ] Nodos acotados que llaman servicios/tools, no repositorios ni SQL libre.
- [ ] Branching por evidencia: `needs_review` y rechazo humanos son rutas reales.
- [ ] Checkpoint por organización/run con retención definida.
- [ ] `interrupt()` + `Approval` verificada antes de acciones externas.
- [ ] Reintentos con límite, timeout, idempotencia y estados `failed`/`timed_out`.
- [ ] Evidencias verificadas; sin secretos ni datos personales reales en estado o logs.
- [ ] Mock determinista y gates ejecutados con evidencia real.

## Referencias
- `TalentOS_SDD.md`: §8.1, §8.3, §9.2, §9.4, §9.5, §10, §11, §15, §16, §21 (Fase 4) y §26.
- `TalentOS_ROADMAP.md`: §3 (Fase 0), §9 (Fase 6, Agent Runtime), §10 (Fase 7, Interview Assistant) y §14 (Fase 11, Simulation Lab & AI Evaluation).
- `AGENTS.md`: LangGraph para flujos con estado, multi-tenancy, tools controladas y reglas de secretos/datos.
- `docs/decisions/`: ADR-006 (LangGraph y aprobación humana), ADR-004 (procesamiento asíncrono) y ADR-009 (mock).
- `docs/DEVELOPMENT_WORKFLOW.md`: registro de evidencia, estados `IN_REVIEW`/`DONE` y checks obligatorios.
- `docs/ENVIRONMENTS.md`: entorno `test` con proveedores mock y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: LangGraph Overview (https://docs.langchain.com/oss/python/langgraph/overview), LangGraph Human-in-the-loop (https://docs.langchain.com/oss/python/langgraph/interrupts), Pydantic (https://docs.pydantic.dev/) y OWASP Top 10 for LLM Applications (https://genai.owasp.org/).
