# TalentOS — Flujo de desarrollo

Aplica a toda tarea del `TalentOS_ROADMAP.md`. El roadmap define qué y en qué orden; el SDD define las restricciones; `AGENTS.md` las reglas del repo. Una tarea se cierra con evidencia, no con una afirmación.

## Principios

1. Una fase por vez; no iniciar una fase si sus dependencias no están satisfechas.
2. Unidades pequeñas y verticales: una tarea entrega comportamiento observable de punta a punta dentro de su fase.
3. Antes de implementar: revisar SDD, skills aplicables y estado real del código. No suponer que una tarea está hecha porque exista un archivo o un doc lo afirme.
4. No marcar DONE sin evidencia de validación. No desactivar nunca tests, lint, typecheck ni controles de seguridad para conseguir una validación artificial: se corrige la causa real del fallo.
5. Si aparece una contradicción entre documentos, código y entorno, detener la parte afectada, explicarla y proponer resolución antes de continuar.
6. Mantener la rama principal funcional; no avanzar a otra fase por iniciativa propia.

## Flujo por tarea

### 1. Plan

- Identificar la tarea pendiente en el roadmap y su fase.
- Leer secciones del SDD concernientes, `AGENTS.md` y cargar las skills de la tabla (SDD 18.1) que apliquen.
- Completar la plantilla de tarea (más abajo): objetivo observable, contexto, alcance, fuera de alcance, dependencias, archivos a tocar, criterios de aceptación, pruebas, validación y riesgos.
- Elegir solo los roles de agente que aporten valor, en este orden (roadmap 20): `planner` → `architect` (si hay impacto estructural) → `backend` o `frontend` → `ai-engineer` (solo IA) → `qa` → `security-reviewer` (si aplica) → `reviewer`. Evitar que dos agentes editen los mismos archivos simultáneamente.
- Declarar supuestos si falta información; elegir la opción más conservadora.

### 2. Unidad vertical

- Implementar solo lo planificado, en el módulo correcto.
- Backend como autoridad: validación Pydantic, autorización por organización y rol, errores uniformes, migración Alembic si cambia el esquema.
- Frontend: estados de carga, vacío, error, éxito, disabled y permisos insuficientes; componentes accesibles.
- IA: contratos de entrada/salida antes del prompt, proveedor mock en tests, evidencias verificables, aprobación humana para acciones externas.
- Sin secretos ni datos personales reales; sin dependencias nuevas sin justificar; sin refactors masivos mezclados con la feature.

### 3. Checks

Ejecutar los aplicables al cambio y registrar comandos con su resultado real:

| Ámbito | Comando |
|---|---|
| Backend lint | `cd apps/api && python -m ruff check .` |
| Backend typecheck | `cd apps/api && python -m mypy app` |
| Backend tests | `cd apps/api && python -m pytest -q` |
| Migraciones | `cd apps/api && alembic check` |
| Frontend typecheck | `cd apps/web && npx tsc --noEmit` |
| Frontend lint | `cd apps/web && npm run lint` |
| Frontend unit | `cd apps/web && npm test -- --run` |
| E2E | `cd apps/web && npm run test:e2e` |
| Playwright browser | `cd apps/web && npx playwright install --with-deps chromium` |
| Infra local | `docker compose config && docker compose up -d` |

Fallos reales se corrigen; no se omiten con skip, `@pytest.mark.skip`, `@vitest`, `xfail`, cambios de umbral, exclusiones de lint ni desactivación de workflows de CI como mecanismo para pasar. Un skip legítimo debe documentar causa, alcance y plan de eliminación, y nunca ocultar un requisito de la tarea.

### 4. Documentación

- Completar la sección `Resultado` de la plantilla de tarea con cambios, comandos ejecutados y pendientes.
- Actualizar `TalentOS_ROADMAP.md`: tabla de progreso (sección 23) y estado de la tarea con evidencia.
- Actualizar docs de la feature, contratos y limitaciones conocidas; crear o modificar ADR en `docs/decisions/` si hay decisión arquitectónica (contexto, decisión, alternativas, consecuencias y fecha).
- Actualizar `AGENTS.md` o `docs/ENVIRONMENTS.md` si cambian reglas, stack o variables de entorno.

### 5. Cierre de fase

- Completar la plantilla de cierre de fase (más abajo) con entregables, criterios con evidencia, comandos, ADRs, deuda, riesgos, cambios de documentación y próxima fase.
- No avanzar si hay fallos críticos, migraciones inconsistentes o criterios sin verificar.
- La Fase 0 cierra cuando un desarrollador puede clonar, configurar y levantar la aplicación siguiendo el README (criterio de salida del roadmap, Fase 0); el README se crea en Fase 1.

## Estados de seguimiento

Usar exclusivamente estos valores en el roadmap y en cualquier reporte de estado:

- `NOT_STARTED` — sin trabajo iniciado.
- `IN_PROGRESS` — trabajo activo; aún no cumple criterios.
- `BLOCKED` — detenido por dependencia o conflicto; documentar causa y desbloqueo.
- `IN_REVIEW` — implementado y con checks ejecutados; pendiente de revisión.
- `DONE` — criterios verificados con evidencia.
- `DEFERRED` — diferido con motivo explícito; no cuenta como completado.

Transiciones habituales: `NOT_STARTED → IN_PROGRESS → IN_REVIEW → DONE`; desde cualquier estado se puede pasar a `BLOCKED` o `DEFERRED` con justificación. Un `BLOCKED` o `DEFERRED` no se reporta como avance de la fase.

## Evidencia obligatoria para `DONE`

Cada tarea `DONE` debe incluir al menos una evidencia verificable, además de los checks que apliquen:

- Comando ejecutado con resultado exitoso (salida o exit code), p. ej. `pytest 12 passed`, `tsc --noEmit exit 0`.
- Test nuevo o modificado que falla antes del cambio y pasa después, cuando sea posible.
- Endpoint verificado con método, ruta y respuesta observada, sin secretos en la salida.
- Captura o grabación de un flujo E2E, cuando corresponda a UI.
- Comportamiento reproducible: pasos concretos y resultado esperado/observado.
- Commit o diff revisado que permita localizar el cambio (cuando exista historial).

Sin evidencia, la tarea permanece `IN_REVIEW`. La evidencia se escribe en el registro de progreso del roadmap; no basta con decir “probado”.

## Plantilla de tarea de implementación (roadmap 21)

```markdown
# TASK-XXX — Nombre de la tarea

## Objetivo
Qué resultado observable se necesita.

## Contexto
Fase y requerimiento del SDD relacionado.

## Alcance
Qué incluye.

## Fuera de alcance
Qué no se debe implementar.

## Dependencias
Tareas, módulos o contratos requeridos.

## Diseño propuesto
Archivos, componentes, servicios y endpoints afectados.

## Criterios de aceptación
- [ ] Criterio observable 1.
- [ ] Criterio observable 2.

## Pruebas
- [ ] Unitarias.
- [ ] Integración.
- [ ] E2E si corresponde.
- [ ] Seguridad si corresponde.

## Validación
Comandos y resultado esperado.

## Riesgos
Riesgos técnicos o de producto.

## Resultado
Resumen de cambios, pruebas ejecutadas y pendientes.
```

## Plantilla de cierre de fase (roadmap 22)

```markdown
# Cierre de fase — Fase X

## Estado
DONE / BLOCKED

## Entregables completados
Lista concreta.

## Criterios de aceptación
Checklist con evidencia.

## Pruebas ejecutadas
Comandos y resultados.

## Decisiones tomadas
ADRs nuevos o modificados.

## Deuda técnica
Pendientes conocidos y justificación.

## Riesgos
Riesgos abiertos.

## Cambios en documentación
Archivos actualizados.

## Próxima fase
Dependencias y primer conjunto de tareas.
```

## Alcance exacto de Fase 1

Entregables de la Fase 1 — Fundación:

- Monorepo: `apps/web`, `apps/api`, `packages/contracts`, `infra/docker`.
- `.gitignore`, `.editorconfig`, formato y lint configurados, README y `.env.example` sin secretos.
- FastAPI: `/health`, `/ready`, settings tipados, errores uniformes, logs con request ID, Ruff y mypy.
- Docker Compose: PostgreSQL, Redis, web, api y worker.
- SQLAlchemy 2.x + Alembic con migración inicial.
- Next.js + TypeScript: layout, página, error y tokens visuales.
- GitHub Actions: lint, typecheck, tests y build.
- Tests smoke de API.

Fuera de alcance: funcionalidad de negocio (auth, vacantes, candidatos, IA) = fases 2+. Sin dependencias nuevas sin justificación documentada.
