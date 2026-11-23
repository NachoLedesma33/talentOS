---
name: devops-deployment
description: Configura Docker Compose, entornos, variables, CI/CD y despliegues de TalentOS con secretos fuera del repo, migraciones controladas y checks obligatorios.
---

# DevOps y Despliegue — TalentOS

## Objetivo

Que un clon limpio arranque de forma reproducible y que cada cambio pase por lint, typecheck, tests, build y validación de migraciones antes de desplegarse. La configuración es código documentado; los secretos nunca lo son.

## Cuándo activarla

- Crear o modificar Docker Compose, Dockerfiles, `infra/docker/` o `infra/scripts/`.
- Añadir variables de entorno o cambiar `.env.example`.
- Modificar GitHub Actions o el orden de checks de CI.
- Preparar `local`, `test`, `staging` o `production`.
- Ejecutar migraciones, builds, rollbacks o despliegues.

## Contexto TalentOS

- Entornos del SDD 17.1: `local` con Docker Compose, `test` aislado con mocks, `staging` de validación, `production` real.
- `docs/ENVIRONMENTS.md` documenta el entorno verificado de esta máquina: Python 3.12.10, Node v24.22.1, npm 12.0.2, Git 2.40.0.windows.1, Docker 29.4.1, Windows.
- `AGENTS.md` fija la secuencia de CI: instalar dependencias reproduciblemente → lint → typecheck → unitarios → integración → build frontend → build backend → escaneo de dependencias → validación de migraciones → deploy a staging tras aprobación.
- Stack: PostgreSQL, Redis, Celery, almacenamiento compatible S3; `/health` y `/ready` son los puntos de chequeo previstos en Fase 1.
- `.env.example` declara nombres sin valores secretos; secretos reales van en variables de entorno o gestor del entorno/CI.
- El modo demo debe arrancar sin credenciales de servicios pagos, con adaptadores mock y datos sintéticos.

## Procedimiento

1. Leer `TalentOS_SDD.md` secciones 17 y 25, `AGENTS.md`, `TalentOS_ROADMAP.md` secciones 3 y 4, `docs/ENVIRONMENTS.md` y `docs/DEVELOPMENT_WORKFLOW.md`.
2. Declarar cada variable nueva en `.env.example` sin valor sensible, en settings tipados del backend y en `docs/ENVIRONMENTS.md`; explicar por qué existe y qué entorno la usa.
3. Leer configuración desde entorno; nunca hardcodear URLs, credenciales, llaves ni banderas de entorno en código o imagen.
4. Definir servicios Docker Compose con versiones fijadas o rangos documentados; `docker compose config` debe pasar antes de `up`.
5. Verificar `/health` y `/ready`: `/ready` debe reflejar dependencias no disponibles, no responder `200` por defecto.
6. Configurar CI con la secuencia de `AGENTS.md`; todos los comandos deben ejecutarse con exit code 0 y registrarse como evidencia.
7. Ejecutar migraciones Alembic en entorno de prueba con aplicación y reversión verificadas; prohibir migraciones destructivas automáticas en producción sin plan de rollback.
8. Construir imágenes con reproducibilidad y tags identificables por commit; no depender de `latest` para despliegues.
9. Inyectar secretos desde el gestor de CI/entorno en tiempo de ejecución; no copiar `.env` a la imagen ni imprimir variables en logs de build.
10. Restringir CORS y URLs públicas por entorno; `staging` y `test` usan datos sintéticos y proveedores mock.
11. Documentar rollback: versión anterior, migración reversible o plan, y cómo verificar que el servicio volvió a `/ready`.
12. Actualizar `docs/ENVIRONMENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, ADR en `docs/decisions/` y roadmap si cambia la configuración.

## Convenciones

- `APP_ENV` controla el entorno; nombres de variables en `UPPER_SNAKE_CASE` y documentados antes de usarse.
- Un cambio de infraestructura pequeño se valida con `docker compose config` y arranque controlado, sin tocar otros módulos.
- Dependencias instaladas de forma reproducible desde manifiesto/lockfile; justificar cualquier dependencia nueva en el PR.
- CI es la misma secuencia que el desarrollador ejecuta localmente; no hay checks “solo en CI”.
- Builds sin red a proveedores pagos; tests usan mocks.
- Secretos rotatorios y con alcance por entorno; rotación probada sin exponer valores.
- Cambios de esquema: migración versionada, `alembic check` y prueba de revert.
- Estado de tarea con evidencia: comando, resultado, entorno y hora, según `docs/DEVELOPMENT_WORKFLOW.md`.

## Anti-patrones

- Commitear `.env`, certificados, tokens de CI o URI con credenciales en `docker-compose.yml`.
- Usar la misma clave en `local`, `staging` y `production`.
- Desactivar tests, lint, typecheck o escaneo de dependencias para desbloquear el deploy.
- Ejecutar migraciones destructivas en producción sin backup y rollback probados.
- Subir CV reales o datos de candidatos a entornos de prueba.
- Decir “funciona en mi máquina” sin `docker compose config` ni evidencia de CI.
- Inventar variables de entorno sin documentarlas en `.env.example` y `docs/ENVIRONMENTS.md`.
- Desplegar sin verificar `/health` y `/ready` después del arranque.

## Validación

- Infra local: `docker compose config && docker compose up -d`, según `docs/DEVELOPMENT_WORKFLOW.md`.
- Backend: `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`, `cd apps/api && alembic check`.
- Frontend: `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`, `cd apps/web && npm test -- --run`; build con los scripts definidos en `apps/web/package.json`.
- E2E: `npx playwright test` cuando el cambio afecta flujos críticos.
- Confirmar en CI que la secuencia de `AGENTS.md` corre en el pull request y que no hay secretos en salida de logs.
- Probar migración idempotente y reversible en entorno de prueba antes de cualquier despliegue.
- En Fase 0, donde las apps y Compose aún no existen, la validación es la relectura de este archivo y el chequeo de rutas citadas.

## Checklist

- [ ] Variables documentadas en `.env.example` y `docs/ENVIRONMENTS.md`, sin secretos.
- [ ] Compose validado y servicios con versiones controladas.
- [ ] `/health` y `/ready` verificados con dependencias reales.
- [ ] CI ejecuta lint, typecheck, tests, builds, auditoría y migraciones.
- [ ] Secretos inyectados por gestor, nunca en imagen ni logs.
- [ ] Migración aplicada y revertida en prueba; rollback documentado.
- [ ] Datos sintéticos y mocks en `test`/`staging`.
- [ ] Evidencia de comandos registrada en el roadmap.

## Referencias

- `TalentOS_SDD.md` secciones 6.3, 17, 25 y `TalentOS_ROADMAP.md` secciones 3 y 4.
- `AGENTS.md` sección “Comandos de validación” y secuencia de CI (SDD 17.4).
- `docs/ENVIRONMENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: FastAPI <https://fastapi.tiangolo.com/>, Next.js <https://nextjs.org/docs>, PostgreSQL <https://www.postgresql.org/docs/>.
