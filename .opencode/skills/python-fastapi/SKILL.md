---
name: python-fastapi
description: Implementa backend FastAPI de TalentOS con Pydantic, servicios de dominio, SQLAlchemy, errores uniformes, autorización por organización y proveedores mock en tests.
---

# Python/FastAPI — TalentOS

## Objetivo
Construir la API de TalentOS en `apps/api/app` con routers delgados, lógica en servicios de dominio y contratos validados. La capa HTTP debe ser autoridad: autenticar, autorizar, validar, auditar y devolver errores consistentes sin exponer secretos ni datos personales.

## Cuándo activarla
- Al crear o modificar routers, esquemas Pydantic, servicios, dependencias, repositorios, workers o manejo de errores en `apps/api/app/`.
- Al añadir endpoints bajo `/api/v1` o cambiar un contrato compartido con `apps/web` / `packages/contracts/`.
- Al integrar un dominio con PostgreSQL, storage o la cola de trabajo.
- Al instrumentar `request_id`, paginación, filtros o códigos HTTP de una operación.
- No activar para diseño de esquema SQL puro: usar `postgresql-data-modeling`; para flujos LangGraph, usar `langgraph-workflows`.

## Contexto TalentOS
- Stack backend: Python 3.12, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic, pytest, Ruff y mypy (SDD §6.2 y `AGENTS.md`).
- Estructura prevista: `apps/api/app/api`, `core`, `domains`, `agents`, `integrations`, `workers`, `observability` y `main.py` (SDD §7).
- Dominios: `identity`, `jobs`, `candidates`, `applications`, `assessment`, `interviews`, `automation`, `agents`, `integrations`, `audit`, `analytics`, `simulation` (SDD §7.1).
- Prefijo `/api/v1`; respuestas consistentes, paginación, filtros, `request_id` y códigos HTTP correctos (SDD §12).
- Estados del SDD §8.3 son enums con transiciones permitidas; los strings del cliente se validan contra el enum, nunca se guardan tal cual.
- Multi-tenancy: `organization_id` se deriva de la sesión/autorización en una dependencia; se verifica membresía y se filtra en repositorio y servicio.
- Human-in-the-loop: escribir/borrar acciones externas o sensibles pasa por `Approval`; el endpoint de decisión verifica quién aprueba y registra auditoría.
- Evidencias: `Evidence` se valida contra `document_id`, candidato y texto confirmado; referencia inexistente → error de contrato o `needs_review`.
- LLM: permisos, validación, estados, persistencia y cálculos son código determinista; el LLM solo se invoca desde la capa de agentes detrás de `LLMProvider`.
- Modo mock: `LLM_PROVIDER=mock` en `local`/`test`; la API arranca sin claves pagas y los tests nunca llaman a un proveedor real (`docs/ENVIRONMENTS.md`).
- Secretos: configuración tipada desde entorno; `.env` no se versiona; errores y logs sin tokens, contraseñas ni CV completo.
- Datos personales: fixtures y seed con candidatos sintéticos; separación entre datos reales y sintéticos.

## Procedimiento
1. Leer el RF en `TalentOS_SDD.md` §4, el endpoint en §12, los límites en §6.4 y las reglas de `AGENTS.md`; comprobar la fase activa en `TalentOS_ROADMAP.md`.
2. Definir primero el contrato Pydantic de entrada/salida con tipos estrictos, enums y ejemplos sintéticos; publicarlo en `packages/contracts/` si lo consume el frontend.
3. Crear el router solo con: dependencias de autenticación/autorización, validación del contrato, llamada al servicio y mapeo de errores a HTTP.
4. Implementar la regla en el servicio del dominio correspondiente; el repositorio SQLAlchemy encapsula consultas y aplica siempre el filtro de organización.
5. Obtener `organization_id` de la dependencia de sesión; rechazar cualquier valor recibido en body/query que intente alterarlo.
6. Para operaciones asíncronas, encolar solo IDs y contexto mínimo con `organization_id`, `actor_id` y `correlation_id`; nunca objetos ORM serializados.
7. Si la operación genera efectos externos o decisiones sensibles, crear `Approval` y dejar el estado en `waiting_approval` hasta decisión humana autorizada.
8. Validar evidencias: cada `evidence_refs` debe pertenecer al documento confirmado del candidato de esa organización; si no, responder error claro o marcar `needs_review`.
9. Registrar auditoría y errores con `request_id`, sin volcar payload sensible; exceptions manejadas de forma central con mensajes accionables.
10. Escribir tests unitarios del servicio, de integración de API y de aislamiento cross-tenant; usar fixtures sintéticas y proveedor mock.
11. Ejecutar Ruff, mypy, pytest y, si el modelo cambió, `alembic check`; adjuntar salida real y actualizar documentación/roadmap.

## Convenciones
- Router delgado, servicio con regla, repositorio con SQL; sin lógica de negocio duplicada en dependencias ni en el endpoint.
- Pydantic v2 con validación estricta; no aceptar `Any` en contratos de API sin justificación documentada.
- Respuestas consistentes con paginación y filtros; IDs públicos UUID y fechas UTC.
- Autorización en cada endpoint y operación de dominio; backend como autoridad, sin confiar en la web.
- Multi-tenancy: toda consulta incluye `organization_id`; los tests incluyen el caso de otra organización intentando el mismo resource_id.
- HITL: herramientas y endpoints de escritura separados de borradores y ejecución; idempotency key en escrituras y registro de quién decidió.
- Evidencia verificable: `quote`, `page`, `document_id` y `checksum` se comprueban contra el texto extraído confirmado; no se acepta una cadena arbitraria del modelo.
- LLMProvider con `generate_structured_output`, `generate_text`, `health_check` y `estimate_usage`; dominio sin importar proveedores concretos.
- Modo mock por entorno: `LLM_PROVIDER=mock`, respuestas deterministas y datasets sintéticos; cambiar a proveedor real no cambia contratos.
- Secretos y datos: valores desde entorno, nunca literales; logs sin API keys, tokens, contraseñas, correos reales ni CV completo.

## Anti-patrones
- Router con reglas de negocio, o servicio que construye consultas SQL por concatenación fuera del repositorio.
- Aceptar `organization_id` del cliente como autoridad o filtrar solo en el frontend.
- LLM desde dominio para permisos, estados, cálculos o persistencia.
- Ejecutar acciones externas sin `Approval`, o autoaprobar decisiones de contratación/descarte.
- Aceptar citas de evidencia sin verificar documento, candidato y organización.
- Inventar endpoints, campos o variables de entorno no documentadas en SDD/`docs/ENVIRONMENTS.md`.
- Logs con payload completo de CV, tokens, secretos o chain-of-thought.
- Tests que dependen de red, proveedor pago, GPU local o datos personales reales.
- Desactivar checks, usar skip/xfail para ocultar fallos o mezclar refactor masivo con la feature.

## Validación
- Unitarios: servicio con casos válidos, inválidos, estado ilegal y evidencia faltante.
- Integración API: POST/GET sobre `/api/v1` con mock, códigos HTTP, paginación, filtros y `request_id` en respuesta.
- Seguridad: usuario sin rol, token inválido y organización distinta → 401/403/404 sin filtrar datos de otra organización.
- Aprobación: acción sin decisión humana no se ejecuta; doble envío con misma idempotency key produce un solo efecto.
- Evidencia: cita inexistente o de otro documento/candidato → rechazo o `needs_review`.
- Mock: suite completa con `LLM_PROVIDER=mock`, sin credenciales ni red pagada.
- Gates: `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`; si cambia el esquema, `cd apps/api && alembic check`.
- En Fase 0 no hay aplicación: validar por relectura de SDD, `AGENTS.md` y `docs/ENVIRONMENTS.md`; no instalar dependencias ni ejecutar gates inexistentes.

## Checklist
- [ ] Contrato Pydantic definido antes del prompt o de la lógica.
- [ ] Router delgado y servicio de dominio dueño de la regla.
- [ ] `organization_id` derivado de sesión y filtrado en repositorio.
- [ ] Estados y errores documentados, con `request_id` y HTTP correcto.
- [ ] Aprobación humana e idempotencia en acciones sensibles.
- [ ] Evidencias verificadas contra documento y candidato de la organización.
- [ ] LLM solo detrás de `LLMProvider`; tests con mock y datos sintéticos.
- [ ] Sin secretos ni datos personales reales en código, logs ni fixtures.
- [ ] Ruff, mypy, pytest y migración validados con evidencia real.

## Referencias
- `TalentOS_SDD.md`: §3.2, §6.4, §7.1, §8.3, §9.6, §10, §12, §14, §16, §17.2 y §25.
- `TalentOS_ROADMAP.md`: §3 (Fase 0), §4 (Fase 1, FastAPI) y fases de dominio correspondientes.
- `AGENTS.md`: stack Python 3.12, comandos de validación, multi-tenancy y reglas de secretos/datos.
- `docs/decisions/`: ADR-001, ADR-003, ADR-004 y ADR-005 aplicables al backend.
- `docs/DEVELOPMENT_WORKFLOW.md`: plantilla de tarea, checks y evidencia para `DONE`.
- `docs/ENVIRONMENTS.md`: `DATABASE_URL`, `REDIS_URL`, `LLM_PROVIDER=mock` y `.env.example` sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: FastAPI (https://fastapi.tiangolo.com/), Pydantic (https://docs.pydantic.dev/), SQLAlchemy (https://docs.sqlalchemy.org/) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
