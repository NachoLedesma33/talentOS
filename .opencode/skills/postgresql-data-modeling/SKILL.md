---
name: postgresql-data-modeling
description: Diseña y migra el esquema PostgreSQL de TalentOS con aislamiento multi-tenant, constraints, índices, estados enum, evidencia verificable y migraciones reversibles.
---

# PostgreSQL Data Modeling — TalentOS

## Objetivo
Mantener un modelo transaccional consistente para reclutamiento, con PostgreSQL como fuente de verdad, Alembic como mecanismo de evolución y aislamiento por organización desde la primera tabla. El esquema debe hacer cumplir integridad que la UI no puede garantizar.

## Cuándo activarla
- Al crear o modificar modelos SQLAlchemy, migraciones Alembic, constraints, índices, enums o consultas de repositorio.
- Al añadir una entidad del SDD §8.1 o cambiar una transición de estados del §8.3.
- Al revisar rendimiento de consultas frecuentes por `organization_id`, estado o fecha.
- Al diseñar seeds de demo o datasets sintéticos para `simulation`.
- No activar para lógica HTTP, contratos Pydantic de endpoint ni render de UI.

## Contexto TalentOS
- PostgreSQL es la fuente de verdad transaccional; SQLAlchemy 2.x es el ORM y Alembic gestiona migraciones (SDD §6.2, ADR-003).
- Entidades iniciales: `User`, `Organization`, `Membership`, `Job`, `JobRequirement`, `JobVersion`, `Candidate`, `CandidateDocument`, `Application`, `Extraction`, `Assessment`, `AssessmentCriterion`, `Evidence`, `InterviewQuestion`, `Automation`, `AutomationRun`, `AgentRun`, `AgentEvent`, `Approval`, `AuditLog`, `Integration`, `SimulationRun` (SDD §8.1).
- Multi-tenancy: todo recurso de negocio lleva `organization_id` propio o heredado por FK; consultas y tareas en background se limitan a la organización autenticada (SDD §3.2).
- Row-Level Security puede añadirse como defensa adicional, pero no reemplaza autorización en aplicación.
- IDs públicos UUID; fechas en UTC; `created_at`/`updated_at` en entidades mutables; foreign keys y unique constraints explícitos; índices en `organization_id`, estados y fechas (SDD §8.2).
- Estados del SDD §8.3: documentos `uploaded → queued → extracting → review_required → confirmed` con `failed`/`rejected`/`deleted`; agentes `pending → running → waiting_approval → completed` con `failed`/`cancelled`/`timed_out`.
- Evidencia: `Evidence` guarda `quote`, `page`, `confidence` y referencia a `document_id`; debe poder verificarse contra el texto extraído y el candidato correcto.
- Human-in-the-loop: `Approval` registra `action_type`, `payload`, `status` y `decided_by`; `AgentRun`/`AgentEvent` permiten inspeccionar pausas y reanudaciones.
- Archivos: la BD guarda metadatos y `storage_key`, nunca el CV completo; secretos de integraciones solo como `encrypted_config_ref`.
- Modo mock: seeds de demo con datos sintéticos y `LLM_PROVIDER=mock`; `simulation` usa datasets ficticios separados de datos reales.
- Sin secretos en migraciones ni constraints; sin nombres, correos ni CVs reales en seeds, fixtures ni documentación.

## Procedimiento
1. Leer `TalentOS_SDD.md` §3.2, §7.1, §8, §9.5 y §11; leer `AGENTS.md` y las ADRs en `docs/decisions/`.
2. Comprobar el esquema actual con `cd apps/api && alembic check` y leer la última revisión aplicada; nunca asumir que la BD local coincide con el código.
3. Identificar la entidad dueña del dato y cómo hereda `organization_id` (directo o vía FK a `Job`, `Candidate` o `Application`).
4. Definir tipos y constraints antes de la migración: UUID, enum con transiciones permitidas, NOT NULL donde el negocio lo exige, UNIQUE para claves naturales y FK con acción explícita.
5. Diseñar índices por patrón de consulta real: filtro por organización + estado + fecha; evitar índices especulativos y medir antes de agregarlos.
6. Si la tabla es sensible, evaluar RLS por organización como capa adicional, documentando que la aplicación sigue siendo responsable de autorizar.
7. Escribir la migración Alembic con `upgrade()` y `downgrade()` reversibles; en producción, cualquier operación destructiva requiere plan de rollback aprobado.
8. Actualizar modelos SQLAlchemy y repositorios para que toda consulta use el contexto de organización; ningún repositorio acepta `organization_id` del cliente sin validación previa del servicio.
9. Crear datos de prueba sintéticos que cubran dos organizaciones, estados inválidos, evidencia de otro documento y aprobación pendiente.
10. Verificar con tests de integración que otra organización no puede leer/actualizar/borrar el recurso; ejecutar migración y reversión en entorno de prueba.
11. Registrar comandos, salida y decisión en documentación/ADR si el cambio afecta límites de dominio.

## Convenciones
- Un Dominio → agregado claro; FK explícitas y sin relaciones bidireccionales que fomenten imports circulares en SQLAlchemy.
- Enums en BD y en Python con los mismos valores; `check constraints` para transiciones o invariantes simples cuando aporten valor.
- Soft delete solo con necesidad de negocio documentada; definir retención y purga real, no dejar filas indefinidas.
- Toda tabla de negocio se puede filtrar por organización; las tablas de auditoría y eventos incluyen `organization_id` y `correlation_id`.
- Evidencia verificable: `quote` y `page` se guardan junto a `document_id`; el repositorio valida pertenencia antes de devolverla al agente o a la UI.
- HITL: estados de aprobación y ejecución de agente se persisten; reanudar un grafo no cambia `decided_by` ni salta una aprobación.
- Modo mock: seeds reproducibles de candidatos sintéticos en `simulation`; reiniciar demo no toca datos reales.
- Secretos: nunca guardar API keys en texto plano; `Integration.encrypted_config_ref` apunta a un almacén cifrado fuera del repo.
- Datos personales: no incluir CVs reales ni correos reales en seeds, tests ni migraciones de ejemplo.
- Logs de SQL parametrizados; no imprimir valores de documentos, tokens ni datos de contacto.

## Anti-patrones
- Tablas de negocio sin `organization_id` o consultas que filtran solo en el frontend.
- Confiar en RLS como única autorización, o desactivarlo “porque ya filtra la API”.
- Guardar el texto completo del CV en la BD de dominio, en logs o en payloads de eventos.
- Estados como strings arbitrarios enviados por el cliente o migraciones que cambian enums sin revisar consumidores.
- Añadir índices por intuición, sin consultas reales ni medición; duplicar índices existentes.
- Migraciones irreversibles, destructivas automáticas en producción o `downgrade()` que no restaura el estado previo.
- Hardcodear credenciales, URLs con secretos o datos personales reales en seeds y fixtures.
- Borrar evidencia o aprobaciones para “limpiar” una ejecución fallida: se registran y corrigen con auditabilidad.
- Crear tablas genéricas “para el futuro” sin caso de uso en el roadmap.

## Validación
- `cd apps/api && alembic check` sin diferencias pendientes después de generar la migración.
- Aplicar y revertir la migración en base de prueba: `upgrade` y `downgrade` exitosos, sin pérdida de esquema previo.
- `cd apps/api && python -m pytest -q`: tests de constraints, unique, FK, enums, índices usados y aislamiento cross-tenant (dos organizaciones, mismo resource_id).
- Caso de evidencia inválida: cita de otro documento, candidato u organización → rechazo o `needs_review`, nunca `supported`.
- Caso HITL: `Approval` pendiente mantiene `AgentRun` en `waiting_approval`; decisión de usuario autorizado cambia estado y queda en `AuditLog`.
- Seeds y fixtures: solo datos sintéticos; búsqueda de correos reales o tokens en diff antes de cerrar.
- `cd apps/api && python -m ruff check .` y `cd apps/api && python -m mypy app` cuando haya código Python.
- En Fase 0 no existe BD ni Alembic: validar por relectura de SDD, `AGENTS.md` y `docs/ENVIRONMENTS.md`; no crear migraciones vacías.

## Checklist
- [ ] Entidad y dueño de `organization_id` identificados.
- [ ] UUID, UTC, timestamps, FK, UNIQUE y NOT NULL revisados.
- [ ] Enums y transiciones de estado alineados con SDD §8.3.
- [ ] Índices justificados por consultas reales de organización/estado/fecha.
- [ ] RLS evaluado como defensa adicional, sin sustituir autorización de aplicación.
- [ ] Migración con `upgrade()` y `downgrade()` verificada en entorno de prueba.
- [ ] Evidencia y aprobaciones modeladas con integridad verificable.
- [ ] Seeds sintéticos, sin secretos ni datos personales reales.
- [ ] Tests cross-tenant y gates ejecutados con evidencia real.

## Referencias
- `TalentOS_SDD.md`: §3.2, §6.4, §7.1, §8, §9.5, §10, §11, §14, §17.2 y §24.
- `TalentOS_ROADMAP.md`: §3 (Fase 0), §4 (Fase 1, PostgreSQL/Alembic) y §5 (Fase 2, multi-tenancy).
- `AGENTS.md`: multi-tenancy por `organization_id`, migraciones y reglas de secretos/datos.
- `docs/decisions/`: ADR-003 (PostgreSQL), ADR-006 y ADR-009 según afecten estados o seeds.
- `docs/DEVELOPMENT_WORKFLOW.md`: evidencia obligatoria, migraciones y Definition of Done.
- `docs/ENVIRONMENTS.md`: `DATABASE_URL`, entorno `test` aislado y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: PostgreSQL (https://www.postgresql.org/docs/), SQLAlchemy (https://docs.sqlalchemy.org/) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
