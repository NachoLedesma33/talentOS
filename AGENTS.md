# TalentOS — Reglas del repositorio

Fuentes de verdad: `TalentOS_SDD.md` (producto, arquitectura y restricciones) y `TalentOS_ROADMAP.md` (orden de entrega y criterios). Este archivo rige a todo agente de código que trabaje en el repositorio. Si documentos, código y entorno se contradicen, se detiene la parte afectada, se explica el conflicto y se propone resolución antes de continuar.

Trabajar solo en la fase activa y en una unidad vertical pequeña. No implementar funcionalidad de negocio futura “por adelantado”. No crear dependencias nuevas sin justificación documentada.

## Stack

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Frontend | Next.js + TypeScript | Aplicación web y UX. |
| UI | Tailwind CSS + componentes accesibles | Sistema visual consistente. |
| Backend | Python 3.12 + FastAPI | API, reglas de negocio y autorización. |
| Validación | Pydantic | Contratos de entrada/salida. |
| ORM | SQLAlchemy 2.x | Persistencia y consultas. |
| Migraciones | Alembic | Evolución versionada del esquema. |
| Datos | PostgreSQL | Fuente de verdad transaccional. |
| Cola / caché | Redis | Broker y caché según necesidad. |
| Worker | Celery o alternativa equivalente | Procesamiento asíncrono. |
| Agentes | LangGraph | Flujos con estado, branching y aprobaciones. |
| Archivos | Storage compatible S3 | Documentos privados. |
| Tests backend | pytest | Unit, integración y API. |
| Tests frontend | Vitest + Testing Library | Componentes y lógica UI. |
| E2E | Playwright | Flujos completos. |
| Calidad | Ruff, mypy/pyright, ESLint | Lint y análisis estático. |
| Local | Docker Compose | Entorno reproducible. |
| CI | GitHub Actions | Checks automáticos. |

Entorno verificado en esta máquina: Python 3.12.10, Node v24.22.1, npm 12.0.2, Git 2.40.0.windows.1, Docker 29.4.1, Windows. Detalle en `docs/ENVIRONMENTS.md`.

## Arquitectura y límites

Monolito modular con procesamiento asíncrono (SDD 6). Módulos backend: `identity`, `jobs`, `candidates`, `applications`, `assessment`, `interviews`, `automation`, `agents`, `integrations`, `audit`, `analytics`, `simulation`. Cada módulo expone servicios y contratos; evitar imports circulares y dependencias que rompan límites. Estructura prevista: `apps/web`, `apps/api`, `packages/contracts`, `infra`, `docs`, `infra/docker`. No crear archivos vacíos de antemano: los módulos se incorporan cuando la fase lo necesita.

- **Backend como autoridad:** el frontend consume la API; nunca decide permisos, calcula reglas de negocio ni accede a PostgreSQL. Routers delgados, lógica en servicios de dominio. Autorización en cada endpoint y operación de dominio.
- **Multi-tenancy por `organization_id`:** todo recurso de negocio pertenece a una organización. Toda consulta se limita a la organización autenticada. No confiar en un `organization_id` enviado por el cliente sin verificar membresía. Las tareas en background transportan el contexto de organización. Los tests comprueban aislamiento cross-tenant.
- **Sin LLM directo en dominio:** permisos, validación, estados, persistencia y cálculos son código determinista. El LLM solo se invoca desde la capa de agentes, detrás de una interfaz `LLMProvider` (`generate_structured_output`, `generate_text`, `health_check`, `estimate_usage`). Los agentes no ejecutan SQL libre, shell ni acceso arbitrario a archivos; sus herramientas son funciones de backend con contratos Pydantic, permisos explícitos, timeout, rate limit, idempotency key en escrituras y registro de invocación. Salidas validadas; evidencias verificables; aprobación humana para acciones externas y decisiones sensibles. Prohibido inferir atributos protegidos, inventar evidencia o decidir contrataciones automáticamente.
- **Proveedores intercambiables:** dominio y agentes desacoplados de proveedores concretos. Adaptadores para proveedor remoto configurable, modelo local opcional y mock determinista. Modelo, endpoint, timeout y límites se configuran por entorno. Integraciones externas también detrás de adaptadores.
- **Modo demo con mocks:** la aplicación arranca sin credenciales de servicios pagos. Datos sintéticos separados de datos reales; seed reproducible y reinicio de demo. Sin prometer inferencia local rápida sin medirla.
- **Contratos y consistencia:** prefijo `/api/v1`; UUID como IDs públicos; fechas UTC; enums y transiciones permitidas en lugar de strings arbitrarios; `request_id`/`correlation_id` en logs; respuestas consistentes con paginación, filtros y códigos HTTP correctos. No duplicar lógica entre frontend y backend; no modificar contratos compartidos sin actualizar consumidores y tests.

## Orden de trabajo obligatorio (SDD 25)

1. Inspeccionar el repositorio antes de modificarlo.
2. Identificar código existente, convenciones y dependencias.
3. Leer el SDD y `AGENTS.md`.
4. Cargar las skills relevantes.
5. Proponer un plan pequeño para la fase solicitada.
6. Identificar archivos, contratos, riesgos y pruebas.
7. Implementar una unidad vertical funcional.
8. Ejecutar lint, typecheck y tests.
9. Corregir errores reales; no ocultarlos ni desactivar checks.
10. Actualizar documentación y reportar lo que quedó pendiente.

Antes de escribir código en Fase 0: inspeccionar entorno y versiones, presentar plan de archivos y dependencias, proponer ADRs iniciales, confirmar compatibilidad del stack y no iniciar fases funcionales hasta cerrar Fase 0.

Reglas del agente (SDD 25): no salirse del alcance aprobado; no inventar endpoints, tablas ni variables de entorno sin documentarlas; no introducir dependencias sin justificar; no usar datos personales reales en fixtures; no poner secretos en código, commits ni logs; no marcar tareas completas sin evidencia; no hacer refactors masivos junto con una feature pequeña; no crear abstracciones genéricas sin un caso de uso real; explicitar supuestos conservadores si falta información; mantener cambios pequeños, revisables y con commits descriptivos.

## Definition of Done (SDD 20)

Una tarea no termina porque compile o porque el agente afirme que la implementó. Aplica lo que corresponda:

- [ ] Requerimiento y criterios de aceptación satisfechos.
- [ ] Código integrado en el módulo correcto.
- [ ] Validaciones de entrada y errores contemplados.
- [ ] Autorización comprobada.
- [ ] Migración creada si cambia el esquema.
- [ ] Tests unitarios e integración relevantes.
- [ ] Tests E2E para flujos críticos.
- [ ] Lint y typecheck correctos.
- [ ] Sin secretos ni datos sensibles en logs.
- [ ] Documentación actualizada.
- [ ] Estados UI completos.
- [ ] Revisión de seguridad para cambios sensibles.
- [ ] Limitaciones conocidas documentadas.

El flujo por tarea, plantillas y política de evidencia están en `docs/DEVELOPMENT_WORKFLOW.md`.

## Skills del proyecto (SDD 18.1)

Ubicación: `.opencode/skills/<skill-id>/SKILL.md`. Cargar la skill según el disparador antes de planificar o implementar. No copiar documentación de frameworks dentro de las skills; referenciar documentación oficial. Skills externas: verificar autor, instrucciones, scripts, permisos y versión antes de adoptarlas; rechazar las que pidan secretos o desactiven validaciones (SDD 18.6).

| Skill ID | Propósito | Cuándo activarla |
|---|---|---|
| `software-architecture` | Modularidad, límites de dominio, dependencias y decisiones arquitectónicas. | Antes de crear módulos o modificar arquitectura. |
| `product-requirements` | Convertir necesidades en historias, criterios de aceptación y alcance. | Antes de implementar funcionalidades nuevas. |
| `frontend-engineering` | Next.js, TypeScript, componentes, estados UI y accesibilidad. | En tareas frontend. |
| `ui-ux-design-system` | Diseño B2B SaaS, tokens, jerarquía visual y consistencia. | Al crear o revisar pantallas. |
| `python-fastapi` | FastAPI, Pydantic, SQLAlchemy, servicios, routers y errores. | En tareas backend. |
| `postgresql-data-modeling` | Esquema, índices, constraints, migraciones y consultas. | Al modificar persistencia. |
| `ai-agent-engineering` | Diseño de agentes, contratos, herramientas, límites y evaluación. | Al implementar IA o workflows. |
| `langgraph-workflows` | Estado, nodos, branching, checkpointing y human-in-the-loop. | En flujos multiagente. |
| `api-integrations-webhooks` | Adaptadores, autenticación, firmas, reintentos e idempotencia. | Al integrar servicios externos. |
| `application-security` | Threat modeling, autorización, secretos, archivos y privacidad. | Antes de exponer endpoints o procesar datos. |
| `testing-quality` | Unit, integration, contract, E2E y AI evaluations. | Antes de cerrar una tarea. |
| `observability-debugging` | Logs, trazas, correlación, métricas y diagnóstico. | Al instrumentar o depurar. |
| `code-review-refactoring` | Revisiones críticas, SOLID cuando aporte valor, deuda y legibilidad. | Antes de integrar cambios. |
| `devops-deployment` | Docker, entornos, CI/CD, configuración y despliegues. | En infraestructura y releases. |
| `technical-documentation` | ADRs, README, contratos y documentación sincronizada. | Al cambiar comportamiento o arquitectura. |

Complementarias (SDD 18.2): `accessibility-a11y`, `performance-optimization`, `privacy-data-governance`, `prompt-injection-defense`, `ai-evaluation-benchmarks`, `release-management`.

## Agentes de desarrollo

Roles de trabajo del asistente de programación (SDD 19), no agentes de reclutamiento del producto. Elegir solo los que aporten valor, en este orden: `planner` → `architect` → `backend` o `frontend` → `ai-engineer` → `qa` → `security-reviewer` → `reviewer`. Evitar ediciones simultáneas de los mismos archivos.

| Rol | Responsabilidad | Restricción |
|---|---|---|
| `planner` | Analizar requerimientos, dividir tareas y detectar dependencias. | No modificar código sin plan aprobado. |
| `architect` | Diseñar módulos, contratos y ADRs. | No introducir complejidad sin justificarla. |
| `backend` | Implementar dominio, API y persistencia. | No saltarse autorización ni validación. |
| `frontend` | Implementar UI y experiencia de usuario. | No modificar contratos backend unilateralmente. |
| `ai-engineer` | Implementar agentes, tools y evaluaciones. | No habilitar acciones externas autónomas. |
| `qa` | Diseñar y ejecutar pruebas. | No reducir cobertura para hacer pasar CI. |
| `security-reviewer` | Revisar amenazas, permisos y exposición de datos. | No aprobar vulnerabilidades críticas abiertas. |
| `reviewer` | Revisar diffs, legibilidad y regresiones. | No aceptar cambios sin ejecutar checks relevantes. |

No se crea `.opencode/agents/`: el flujo ya queda definido aquí y en `docs/DEVELOPMENT_WORKFLOW.md`. Si OpenCode lo requiere más adelante, se crea con estos mismos roles.

## Comandos de validación

Ejecutar solo los aplicables al cambio; todos deben terminar con éxito antes de marcar DONE. La estructura `apps/web` y `apps/api` se crea en Fase 1; en Fase 0 la validación es la relectura de los archivos de documentación creados.

| Ámbito | Comando | Cuándo |
|---|---|---|
| Backend lint | `cd apps/api && python -m ruff check .` | Todo cambio Python. |
| Backend typecheck | `cd apps/api && python -m mypy app` | Todo cambio Python. |
| Backend tests | `cd apps/api && python -m pytest -q` | Dominio, API, integración. |
| Migraciones | `cd apps/api && alembic check` | Cambios de modelo/esquema. |
| Frontend typecheck | `cd apps/web && npx tsc --noEmit` | Todo cambio TypeScript. |
| Frontend lint | `cd apps/web && npm run lint` | Todo cambio frontend. |
| Frontend unit | `cd apps/web && npm test -- --run` | Componentes y lógica UI. |
| E2E | `npx playwright test` | Flujos críticos. |
| Compose | `docker compose config && docker compose up -d` | Cambios de infraestructura local. |

CI (SDD 17.4): instalar dependencias reproduciblemente → lint → typecheck → unitarios → integración → build frontend → build backend → escaneo de dependencias → validación de migraciones → deploy a staging tras aprobación. No ejecutar migraciones destructivas automáticas en producción sin plan de rollback. Nunca desactivar tests, lint, typecheck ni controles de seguridad para obtener una validación artificial.

## Secretos y datos

- Secretos solo en variables de entorno o gestor de secretos; `.env` nunca se versiona; `.env.example` sin valores secretos.
- No pegar API keys, tokens, contraseñas ni credenciales en código, commits, logs, mensajes de error, issues ni documentación.
- No usar datos personales reales ni CVs reales en fixtures, tests, demo ni logs; usar datos sintéticos.
- Logs sin tokens, contraseñas, CV completos ni información personal innecesaria; no registrar chain-of-thought.
- Si se detecta un secreto expuesto, detener el trabajo, no reescribir el historial por iniciativa propia y reportar el hallazgo.
