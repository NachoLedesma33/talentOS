---
name: software-architecture
description: Delimita módulos, dependencias y contratos de TalentOS antes de crear o modificar estructura, servicios o flujos entre dominios.
---

# Software Architecture — TalentOS

## Objetivo
Mantener el monolito modular descrito en `TalentOS_SDD.md` con límites explícitos entre dominios, contratos compartidos y decisiones registradas. Esta skill evita que una tarea pequeña introduzca microservicios, imports cruzados o autorización duplicada.

## Cuándo activarla
- Antes de crear módulos en `apps/api/app/domains/`, `apps/api/app/agents/`, `apps/api/app/workers/` o contratos en `packages/contracts/`.
- Al agregar un endpoint, evento, tabla o herramienta de agente que cruce dos dominios.
- Al proponer una ADR nueva o revisar ADR-001 a ADR-009 en `docs/decisions/`.
- Al cambiar el flujo de una solicitud: web → API → dominio → PostgreSQL/storage/cola → worker → grafo IA.
- No activar para cambios de texto, estilos aislados ni correcciones de un solo archivo sin impacto estructural.

## Contexto TalentOS
- Stack acordado: Next.js + TypeScript en `apps/web`, FastAPI + Pydantic + SQLAlchemy 2.x en `apps/api`, PostgreSQL, Redis/Celery, LangGraph y almacenamiento privado (SDD §6.2).
- Dominios backend: `identity`, `jobs`, `candidates`, `applications`, `assessment`, `interviews`, `automation`, `agents`, `integrations`, `audit`, `analytics`, `simulation` (SDD §7.1).
- Todo recurso de negocio pertenece a una organización: `organization_id` se deriva de la sesión/autorización, nunca del cuerpo enviado por el cliente (SDD §3.2).
- El frontend consume API; no decide permisos, no accede a PostgreSQL y no construye reglas de negocio.
- Los agentes solo llaman tools de backend autorizadas: sin SQL libre, shell ni filesystem arbitrario (SDD §6.4 y §10).
- Las decisiones finales de selección requieren revisión humana; el orquestador puede pausar en `waiting_approval`, pero no aprobar por su cuenta.
- Cada conclusión debe apoyarse en `evidence_refs` verificables o marcarse `not_found`/`needs_review` (SDD §9.5).
- El modo demo/desarrollo funciona con `LLM_PROVIDER=mock` y datos sintéticos; la arquitectura no cambia al sustituir el proveedor (ADR-005 y ADR-009).
- Fase 0 es descubrimiento y baseline: no crear código de negocio ni dependencias nuevas sin justificación (`TalentOS_ROADMAP.md` §3).

## Procedimiento
1. Leer `TalentOS_SDD.md` §3.2, §6, §7, §24 y §25; leer `TalentOS_ROADMAP.md` §3 y la fase activa; leer `AGENTS.md` y las ADRs presentes en `docs/decisions/`.
2. Inspeccionar el repositorio antes de proponer cambios: listar módulos, contratos y dependencias existentes; no asumir estructura que aún no existe.
3. Escribir el alcance en una frase: qué dominio es dueño del dato, qué dominio consume el contrato y qué servicio ejecuta la regla.
4. Trazar el flujo completo de extremo a extremo, incluyendo organización activa, actor autenticado, persistencia, evento, worker y estado visible en UI.
5. Definir el contrato primero (schema de entrada/salida, enumeraciones de estado, códigos de error e idempotency key en escrituras); publicarlo en `packages/contracts/` cuando aplique.
6. Revisar límites: el router solo valida y delega; el servicio de dominio contiene la regla; el repositorio encapsula SQL; el agente invoca tools, no tablas.
7. Comprobar el aislamiento multi-tenant en cada capa, incluyendo tareas asíncronas y mensajes: el `organization_id` viaja en el contexto mínimo del job, no en un objeto ORM serializado.
8. Identificar el punto de aprobación humana si hay acción externa, cambio de etapa sensible o decisión de selección; modelarlo como estado `waiting_approval` y `Approval` en el dominio correspondiente.
9. Para cualquier resultado de IA, exigir referencias a documento/candidato/vacante de la misma organización; si no existen, el contrato debe permitir `needs_review`.
10. Si la decisión es estructural, crear o actualizar una ADR en `docs/decisions/` con contexto, decisión, alternativas, consecuencias y fecha antes de implementar.
11. Ejecutar la validación de esta skill y adjuntar salida real (comando + resultado) al reporte de la tarea; actualizar `docs/DEVELOPMENT_WORKFLOW.md` si cambia el flujo de trabajo.

## Convenciones
- Un dominio expone servicios y contratos; evita importar schemas internos de otro dominio. Usa contratos compartidos para lo que cruza límites.
- Dependencias hacia adentro: `api → domains → repositories`; ningún repositorio importa routers, ni un dominio de bajo nivel importa `agents` o `integrations`.
- `organization_id` se obtiene de la sesión autorizada y se filtra en la consulta; los IDs de recursos del cliente se validan contra la organización activa.
- Toda herramienta de agente declara permiso, límite de payload, timeout e idempotency key; las herramientas de lectura, borrador y ejecución son distintas.
- Los eventos usan el envelope de SDD §11.1 con `organization_id`, `correlation_id` y `payload_version`; consumidores idempotentes.
- Los estados son enums con transiciones permitidas (`uploaded → queued → extracting → review_required → confirmed`; `pending → running → waiting_approval → completed`), no strings libres desde la UI.
- Evidencia verificable: `evidence_refs` apunta a `document_id`, `page` y `quote` reales del texto confirmado; una cita inexistente invalida el resultado o fuerza revisión.
- Modo mock: cualquier flujo nuevo debe poder ejecutarse con `LLM_PROVIDER=mock` y fixtures sintéticas sin credenciales pagas.
- Secretos: configuración tipada desde entorno; nunca literals en código, tests, logs, excepciones ni mensajes de error al cliente.
- Datos personales: fixtures con candidatos sintéticos; ningún CV, email o nombre real en repositorio, logs ni ejemplos de documentación.

## Anti-patrones
- Crear microservicios, colas adicionales o paquetes genéricos sin un caso de uso real del roadmap.
- Router con reglas de negocio, o servicio que construye SQL dinámico fuera del repositorio.
- Confiar en `organization_id` recibido del frontend o en permisos calculados en la web.
- Agente con SQL libre, shell, acceso a filesystem, o tool que pueda enviar mensajes sin `request_human_approval`.
- Autoaprobación de rechazos, contrataciones o acciones externas; sustituir revisión humana por "confianza del modelo".
- Presentar ranking opaco o recommendation sin criterios, evidencias y limitaciones.
- Inventar evidencia, rellenar datos faltantes por inferencia o mezclar evidencia de otro candidato/documento.
- Hardcodear API keys, URLs privadas o datos personales reales en código, tests o fixtures.
- Depender de un proveedor LLM pago para ejecutar tests o la demo local.

## Validación
- Casos obligatorios: dos organizaciones accediendo al mismo resource_id → 404/403 sin fuga; job en background con contexto cross-tenant → rechazado.
- Contrato: schema inválido, enum de estado desconocido y `evidence_refs` inexistente → error claro o `needs_review`, nunca resultado `supported`.
- Aprobación: acción externa sin `Approval` resuelto por usuario autorizado → no se ejecuta; reintento con misma idempotency key → un solo efecto.
- Mock: ejecutar el flujo completo con `LLM_PROVIDER=mock` y dataset sintético; ningún test llama a proveedor real.
- Gates aplicables cuando exista código (Fase 1+): `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`, `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`; si el esquema cambia, `cd apps/api && alembic check`.
- En Fase 0 la evidencia es la relectura de los archivos de documentación creados y el ADR revisado: no ejecutar gates de código aún inexistente ni marcar tareas completadas sin revisión real.
- Adjuntar al reporte el comando ejecutado, su salida y el archivo de decisión/docs actualizado; sin evidencia la tarea permanece `IN_REVIEW` (`docs/DEVELOPMENT_WORKFLOW.md`).

## Checklist
- [ ] Leídos SDD, roadmap, `AGENTS.md` y ADRs aplicables antes de decidir.
- [ ] Dominio dueño del dato y consumidores del contrato identificados por escrito.
- [ ] `organization_id` derivado de sesión y filtrado en consultas, eventos y jobs.
- [ ] Punto de human-in-the-loop modelado para acciones externas o decisiones sensibles.
- [ ] `evidence_refs` verificables o estado `needs_review` en el contrato.
- [ ] Flujo ejecutable en modo mock con datos sintéticos.
- [ ] Sin secretos, sin datos personales reales y sin logs con contenido de CV.
- [ ] ADR creada/actualizada si el cambio es estructural.
- [ ] Validación ejecutada con evidencia real adjunta.

## Referencias
- `TalentOS_SDD.md`: §1.2, §3.2, §6, §7, §9.5, §10, §11, §24, §25 y §26.
- `TalentOS_ROADMAP.md`: §3 (Fase 0) y §4 (Fase 1, fundación del monorepo).
- `AGENTS.md`: reglas vigentes del repositorio; prioridad sobre supuestos del agente.
- `docs/decisions/`: ADR-001 a ADR-009; formato descrito en `TalentOS_SDD.md` §24.
- `docs/DEVELOPMENT_WORKFLOW.md`: flujo por tarea, evidencia para `DONE` y Definition of Done.
- `docs/ENVIRONMENTS.md`: versiones reales, entornos, `LLM_PROVIDER=mock` y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: OpenCode Skills (https://opencode.ai/docs/skills/) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
