---
name: product-requirements
description: Convierte necesidades de reclutamiento en historias, criterios de aceptación verificables y alcance por fase para TalentOS, evitando features fuera del MVP.
---

# Product Requirements — TalentOS

## Objetivo
Traducir cada requerimiento funcional del SDD en una unidad vertical pequeña, observable y verificable antes de escribir código. El resultado debe dejar claro qué se entrega, qué queda fuera, qué evidencia demuestra el cumplimiento y qué decisión humana se preserva.

## Cuándo activarla
- Antes de implementar cualquier RF de `TalentOS_SDD.md` §4 o tarea de `TalentOS_ROADMAP.md`.
- Cuando una petición llegue como idea amplia: “quiero que la IA analice CVs”, “queremos automatizar correos”, “queremos un dashboard de agentes”.
- Cuando haya ambigüedad sobre roles, estados, mensajes de error o criterios de aceptación.
- Al priorizar entre P0, P1 y P2 o al detectar que una solicitud pertenece a una fase posterior.
- No activar para corregir un bug con criterio ya documentado ni para decisiones puramente de estilo visual.

## Contexto TalentOS
- MVP y fuera de MVP están definidos en SDD §2: no videollamadas, no análisis facial/de voz, no decisiones automáticas de contratación, no envíos masivos sin aprobación.
- Requerimientos P0: autenticación, organizaciones, vacantes, candidatos, extracción con revisión, matching por criterios, ejecución de flujos, aprobaciones, automatizaciones, auditoría, simulación y métricas (SDD §2.1 y §4).
- Roles iniciales: Owner, Admin, Recruiter, Reviewer, Viewer (SDD §3.1); cada historia debe declarar quién puede ejecutarla.
- Multi-tenancy: todo recurso pertenece a una organización; el criterio de aceptación debe comprobar que otra organización no lo ve.
- Human-in-the-loop: acciones externas y decisiones sensibles requieren aprobación; la historia no puede dar por terminada una acción con solo «IA lo sugirió».
- Evidencias: cada resultado de matching debe rastrearse a una cita real del documento confirmado o marcarse `not_found`/`needs_review`.
- Modo demo: criterios deben ser verificables con `LLM_PROVIDER=mock` y datos sintéticos; ninguna aceptación depende de credenciales pagas.
- Seguridad: sin secretos en historias, ejemplos o fixtures; sin CVs ni nombres reales en documentación de producto.
- Plantilla de tarea y política de evidencia: `docs/DEVELOPMENT_WORKFLOW.md`; fases y orden: `TalentOS_ROADMAP.md`.

## Procedimiento
1. Leer `TalentOS_SDD.md` §2, §3, §4 y §21; leer la fase activa en `TalentOS_ROADMAP.md`; leer `AGENTS.md` y `docs/DEVELOPMENT_WORKFLOW.md`.
2. Identificar el ID del requerimiento (por ejemplo RF-032) y su prioridad; si no existe, registrar el supuesto y proponer el RF nuevo sin inventarlo como existente.
3. Escribir el resultado observable en una frase: actor, acción, recurso y respuesta esperada.
4. Delimitar alcance y fuera de alcance, indicando la fase del roadmap a la que pertenece; deferir lo que sea P1/P2 o fuera del MVP.
5. Desglosar en criterios de aceptación observables con: rol autorizado, organización activa, datos de entrada, salida, estados y errores.
6. Agregar criterios transversales aplicables: aislamiento cross-tenant, aprobación humana cuando corresponda, evidencia verificable, ejecución en modo mock, ausencia de secretos y datos sintéticos.
7. Listar contratos, tablas, endpoints, eventos o pantallas afectadas; marcar los que requieran actualización de tests y documentación.
8. Definir la prueba que demostrará cada criterio antes de implementar: unitaria, integración, API, componente o E2E; describir el caso que debe fallar antes del cambio.
9. Verificar que la unidad sea vertical y pequeña; si cruza dos fases o dominios sin dependencia real, dividirla.
10. Tras implementar, ejecutar la validación, adjuntar evidencia real y actualizar el estado en `TalentOS_ROADMAP.md` según `docs/DEVELOPMENT_WORKFLOW.md`.

## Convenciones
- Un RF produce una o más historias con criterios numerados y trazables al ID del SDD; sin criterio observable, la historia no está lista.
- Criterios con verbos verificables: “el recruiter ve…”, “la API responde 403…”, “el agente queda en `waiting_approval`…”. Evitar “debe ser intuitivo”.
- La autorización se expresa por rol y organización; backend como autoridad, sin criterios que dependan de estado oculto en el frontend.
- Estados del dominio se nombran con los enums del SDD (`uploaded`, `extracting`, `review_required`, `waiting_approval`, `needs_review`), no con adjetivos libres.
- Aprobación humana: criterio separado para quién solicita, quién decide y qué queda registrado en auditoría.
- Evidencia verificable: criterio que exige `evidence_refs` válidos o etiqueta explícita de dato no encontrado; nunca "explicación convincente" sin fuente.
- Demo: todo criterio debe poder demostrarse con dataset sintético y proveedor mock; el proveedor real es cambio de configuración, no de alcance.
- Secretos y datos: ejemplos con correos y nombres ficticios; ningún valor real de API key, token o CV en historia, test ni documentación.
- Si falta información, declarar supuesto conservador y mantener la historia en `IN_PROGRESS`; no inventar endpoint, tabla o variable de entorno.

## Anti-patrones
- Historias tipo “mejorar la IA” o “hacer el dashboard” sin RF, actor, salida y prueba asociada.
- Mezclar varios RFs en una sola entrega grande o adelantar trabajo de fases futuras “por si sirve”.
- Aceptar como evidencia una captura sin comando, una afirmación verbal o un test que no fallaba antes del cambio.
- Definir aprobación humana solo en la UI, sin estado persistido ni registro de quién decidió.
- Criterios que dependan de un proveedor LLM pago, de GPU local sin medir o de datos personales reales.
- Incluir atributos protegidos, inferencias de personalidad o ranking opaco como requisito.
- Escribir ejemplos con CVs reales, correos corporativos, tokens o URLs con credenciales.
- Marcar `DONE` sin actualizar roadmap/docs ni registrar limitaciones conocidas.

## Validación
- Matriz RF → criterios → tests: cada criterio tiene al menos una prueba identificada; cada prueba nombra el caso que fallaría sin el cambio.
- Revisar cobertura de los seis transversales aplicables: multi-tenant, HITL, evidencia, mock, secretos y datos sintéticos.
- En Fase 0, evidencia = relectura de SDD, roadmap, `AGENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md` y la plantilla completada; no ejecutar gates de código inexistente.
- Cuando exista código, ejecutar los aplicables y registrar salida real: `cd apps/api && python -m pytest -q`, `cd apps/web && npm test -- --run`, `npx playwright test` para flujos críticos.
- Para cambios de esquema o frontend, añadir `cd apps/api && alembic check` y `cd apps/web && npx tsc --noEmit` según corresponda.
- Sin evidencia, la tarea queda `IN_REVIEW`; no usar skip, xfail ni umbrales relajados para simular cumplimiento.

## Checklist
- [ ] RF de origen y prioridad citados; fase del roadmap confirmada.
- [ ] Resultado observable con actor, acción, recurso y respuesta.
- [ ] Alcance y fuera de alcance explícitos.
- [ ] Roles y organización activa incluidos en los criterios.
- [ ] Aprobación humana modelada si hay acción externa o decisión sensible.
- [ ] Evidencia verificable o `needs_review` exigido en los criterios.
- [ ] Demo posible con `LLM_PROVIDER=mock` y datos sintéticos.
- [ ] Sin secretos ni datos personales reales en historias o ejemplos.
- [ ] Prueba definida por criterio y evidencia real adjunta al cierre.

## Referencias
- `TalentOS_SDD.md`: §1.2, §2, §3, §4, §16, §20, §21 y §25.
- `TalentOS_ROADMAP.md`: §1 (reglas de ejecución), §3 (Fase 0) y §21 (plantilla de tarea).
- `AGENTS.md`: orden de trabajo obligatorio, Definition of Done y reglas de secretos/datos.
- `docs/decisions/`: ADRs que puedan limitar el alcance de la historia.
- `docs/DEVELOPMENT_WORKFLOW.md`: flujo por tarea, plantilla, estados y evidencia obligatoria para `DONE`.
- `docs/ENVIRONMENTS.md`: entornos `local`/`test`, `LLM_PROVIDER=mock` y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: OpenCode Documentation (https://opencode.ai/docs/) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
