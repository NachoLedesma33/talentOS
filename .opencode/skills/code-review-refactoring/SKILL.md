---
name: code-review-refactoring
description: Revisa cambios de TalentOS antes de integrarlos, con foco en alcance, multi-tenancy, seguridad, contratos, tests y deuda, y refactoriza solo cuando aporte valor verificable.
---

# Code Review y Refactoring — TalentOS

## Objetivo

Mantener cambios pequeños, correctos y revisables. La revisión detecta riesgos reales de tenant, seguridad y contrato antes de integrar; el refactoring mejora legibilidad o estructura sin mezclarse con features ni cambiar comportamiento por accidente.

## Cuándo activarla

- Antes de marcar una tarea `IN_REVIEW` o pedir merge.
- Al revisar un diff propio o ajeno, especialmente si toca autorización, DB, agentes o webhooks.
- Al acumular deuda que dificulta una tarea actual.
- Al duplicar lógica entre frontend y backend o entre módulos.
- Al cambiar contratos compartidos en `packages/contracts/`.

## Contexto TalentOS

- `AGENTS.md` define Definition of Done: criterios, módulo correcto, validación, autorización, migración si aplica, tests, lint/typecheck, sin secretos en logs, documentación y limitaciones.
- `docs/DEVELOPMENT_WORKFLOW.md` exige evidencia real para `DONE` y prohíbe ocultar fallos con skip, xfail, exclusiones de lint o workflows desactivados.
- El SDD 25 prohíbe refactors masivos junto con features pequeñas, abstracciones genéricas sin caso de uso y cambios de contrato sin actualizar consumidores y tests.
- La arquitectura es monolito modular con módulos `identity`, `jobs`, `candidates`, `applications`, `assessment`, `interviews`, `automation`, `agents`, `integrations`, `audit`, `analytics`, `simulation`.
- Backend es autoridad: routers delgados, lógica en servicios de dominio; frontend no decide permisos ni reglas de negocio.

## Procedimiento

1. Leer `AGENTS.md`, `TalentOS_SDD.md` sección 25 y 18.4, `docs/DEVELOPMENT_WORKFLOW.md` secciones “Checks”, “Documentación” y “Evidencia”, y la skill de testing aplicable.
2. Acotar el diff: si mezcla varias unidades verticales o toca archivos sin relación con la tarea, devolverlo para dividir.
3. Verificar comportamiento observable contra criterios de aceptación; revisar casos de error, vacío, carga y permisos insuficientes.
4. Revisar seguridad: `organization_id` del contexto autenticado en cada consulta, rol necesario, firma anti-replay en webhooks, secretos fuera del repo, redacción de logs y MIME real en uploads.
5. Revisar datos: migración Alembic si cambia el esquema, índices/constraints coherentes, sin datos personales reales en fixtures.
6. Revisar contratos: esquemas Pydantic y `packages/contracts/`; si cambia un contrato, productor, consumidor, tests y docs deben estar en el mismo diff.
7. Revisar IA: salida validada, evidencia citada verificable, aprobación humana para acciones externas; sin ranking opaco ni evidencia de datos inexistente.
8. Revisar observabilidad: `correlation_id` presente, errores categorizados y sin chain-of-thought en logs.
9. Revisar documentación: README, `docs/ENVIRONMENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, ADR en `docs/decisions/` y roadmap actualizados si el cambio lo exige.
10. Para refactoring, exigir tests previos, un propósito concreto (eliminar duplicación real, reducir acoplamiento, aclarar nombre) y diff separado de la feature.
11. Aplicar SOLID solo cuando resuelva un problema concreto; preferir funciones pequeñas y contratos explícitos antes que jerarquías especulativas.
12. Emitir comentarios accionables: ubicación, problema, impacto y corrección concreta. Ningún comentario reemplaza una prueba.

## Convenciones

- Un comentario de revisión = un problema verificable; si no se puede demostrar, no se bloquea.
- Bloquear: filtración cross-tenant, secreto expuesto, contrato roto, evidencia falsa, check desactivado.
- Solicitar cambios: error sin test, documentación desincronizada, nombre ambiguo, deuda que impacta la tarea actual.
- Sugerir: micro-mejora de legibilidad sin cambiar comportamiento ni ampliar alcance.
- Prefijo `/api/v1`, UUID como IDs públicos, fechas UTC y errores consistentes.
- Los refactors conservan comportamiento; cualquier cambio observable necesita test y documentación.
- Revisar primero lo que puede dañar datos o personas; estilo al final.

## Anti-patrones

- Aprobar porque “los tests pasan” sin revisar autorización ni tenant.
- Pedir abstracciones genéricas, factories o capas para un solo caso de uso.
- Mezclar renombrados masivos con arreglo de bug.
- Cambiar un esquema sin ejecutar contract tests ni avisar al consumidor.
- Resolver un fallo de CI con `skip`, `xfail`, excepción de lint o desactivando workflow.
- Aceptar salida de IA sin evidencia verificable o con datos inventados.
- Escribir comentarios de estilo interminables que ocultan un riesgo de seguridad.
- Reportar DONE sin comandos ni resultado real adjunto.

## Validación

- Ejecutar según el cambio: `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`, `cd apps/api && alembic check`, `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`, `cd apps/web && npm test -- --run`, `npx playwright test`.
- Repetir el test de regresión que motivó el cambio y comprobar que falla sin el fix cuando sea posible.
- Verificar que el diff no incluye secretos, `.env`, datos personales reales ni archivos generados.
- Verificar que cada check desactivado tenga justificación documentada y plan de eliminación; si no, rechazar.
- Confirmar que el estado del roadmap y la evidencia siguen `docs/DEVELOPMENT_WORKFLOW.md`.
- En Fase 0, donde las apps aún no existen, la validación es la relectura de este archivo y el chequeo de rutas citadas.

## Checklist

- [ ] Diff acotado a una unidad vertical de la fase activa.
- [ ] Criterios de aceptación y casos de error comprobados.
- [ ] Autorización y cross-tenant revisados con test.
- [ ] Secretos, logs y uploads revisados.
- [ ] Contratos, consumidores y tests sincronizados.
- [ ] Migración incluida si cambia esquema.
- [ ] Refactor separado, con tests y propósito concreto.
- [ ] Documentación y evidencia de checks presentes.

## Referencias

- `AGENTS.md` secciones “Orden de trabajo obligatorio”, “Definition of Done” y “Secretos y datos”.
- `TalentOS_SDD.md` secciones 18.4, 24, 25 y `TalentOS_ROADMAP.md` sección 3.
- `docs/DEVELOPMENT_WORKFLOW.md`, `docs/ENVIRONMENTS.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: FastAPI <https://fastapi.tiangolo.com/>, Pydantic <https://docs.pydantic.dev/>, Next.js <https://nextjs.org/docs>.
