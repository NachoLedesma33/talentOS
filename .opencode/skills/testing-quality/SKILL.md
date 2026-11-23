---
name: testing-quality
description: Diseña y ejecuta unit, integración, contract, E2E y evaluaciones IA de TalentOS, con tests cross-tenant, fidelidad de evidencia y CI obligatoria antes de cerrar una tarea.
---

# Testing y Calidad — TalentOS

## Objetivo

Demostrar que cada unidad vertical funciona, respeta el aislamiento multi-tenant y presenta evidencia verificable. Una tarea no se cierra por “compila”: se cierra con lint, typecheck, tests y evaluaciones en verde.

## Cuándo activarla

- Antes de marcar completada cualquier historia, feature o arreglo.
- Al crear contratos, endpoints, reglas de dominio, migraciones o flujos de agentes.
- Al cambiar prompts, modelos, workflows o esquemas de evidencia.
- Al corregir un bug: la regresión debe quedar cubierta.
- Al revisar CI o investigar tests intermitentes.

## Contexto TalentOS

- La pirámide del SDD (sección 16.1) incluye unitarias, integración, contract tests, E2E y AI evaluations.
- Criterios mínimos (SDD 16.2): ningún endpoint permite acceso cross-tenant; ningún resultado de matching se muestra sin criterios y evidencias; los tests no dependen de un proveedor LLM pago; lint, typecheck y tests corren en CI.
- Backend: `pytest`; frontend: Vitest + Testing Library; E2E: Playwright; contratos compartidos: `packages/contracts/`.
- Las evaluaciones usan dataset sintético versionado con CV incompletos, ambiguos, contradictorios, malformados y con prompt injection (SDD 15.3).
- `docs/DEVELOPMENT_WORKFLOW.md` es la fuente de los comandos reales; `docs/ENVIRONMENTS.md` describe `test` con datos aislados y mocks.

## Procedimiento

1. Leer criterios de aceptación, `TalentOS_SDD.md` secciones 15 y 16, `AGENTS.md`, `TalentOS_ROADMAP.md` sección 3 y `docs/DEVELOPMENT_WORKFLOW.md`.
2. Escribir primero la lista de comportamientos observables: caso happy path, error, permiso, tenant y evidencia.
3. Unit tests: reglas de dominio, transiciones de estado, cálculos, validadores, permisos e idempotencia. Sin base de datos ni red.
4. Integration tests: repositorios con PostgreSQL, API con autenticación, storage, cola/worker, adaptadores LLM mockeados y webhooks.
5. Contract tests: esquemas entrada/salida de agentes, eventos internos, proveedores y contrato frontend/backend en `packages/contracts/`.
6. E2E con Playwright: registro/login, crear vacante, cargar CV, revisar extracción, ejecutar matching, aprobar acción y consultar auditoría.
7. AI evaluations: ejecutar el dataset sintético versionado ante cada cambio de prompt, modelo o workflow; medir exactitud, JSON válido, consistencia, robustez ante prompt injection, latencia, costo y tasa de intervención humana.
8. Fidelidad de evidencia: assertions verifican que cada conclusión cita un fragmento existente del documento; si falta, el resultado debe decir “no encontrado”, nunca inventar evidencia.
9. Cross-tenant: crear dos organizaciones sintéticas y comprobar que cada endpoint, consulta, webhook y worker rechaza acceso del tenant A a datos del B.
10. Hacer deterministas los tests: reloj y IDs controlados, fixtures sintéticas, sin llamadas externas, sin orden dependiente entre casos.
11. Ejecutar la secuencia completa de CI local antes de pedir revisión y adjuntar resultado real; no silenciar fallos con `skip`, `xfail` o aumentos ciegos de timeout.
12. Si el bug es de producción, agregar el test de regresión antes del fix o en el mismo cambio.

## Convenciones

- Nombre de test describe comportamiento y contexto, no implementación: “rechaza evento duplicado de otra organización”.
- Un escenario por assertion relevante; fixtures reutilizables, sin copiar CV de muestra con datos personales.
- Proveedores externos siempre detrás de un adapter mock; el modo demo funciona sin credenciales.
- Errores esperados se comprueban por tipo y código, no por texto libre.
- Los cambios de contrato actualizan productor, consumidor, tests y documentación en el mismo PR.
- Métricas de IA se registran con versión de dataset, prompt y modelo para comparar regresiones.
- Cobertura se usa como señal de riesgo en zonas críticas (autorización, tenant, idempotencia), no como meta vacía.

## Anti-patrones

- Test que llama a un LLM real, a un proveedor de pago o a internet durante CI.
- Usar datos personales reales en fixtures, screenshots o logs de test.
- Verificar solo el `200`: no comprobar qué datos se devolvieron ni a qué tenant pertenecen.
- Aceptar salida de IA sin validar esquema ni existencia de la evidencia citada.
- Marcar un test intermitente como “flaky” o repetirlo hasta que pase.
- Dar por válido un matching sin criterios, snippet o marca explícita de dato faltante.
- Cambiar esquema sin ejecutar contract tests de todos los consumidores.
- Saltarse lint/typecheck porque “los tests pasan”.

## Validación

- Usar los comandos de `docs/DEVELOPMENT_WORKFLOW.md`: `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app`, `cd apps/api && python -m pytest -q`, `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`, `cd apps/web && npm test -- --run` y `npx playwright test`, según aplique.
- En Fase 0, donde `apps/api` y `apps/web` aún no existen, la validación es la relectura de este archivo y el chequeo de rutas citadas.
- Repetir la suite E2E y los tests de integración dos veces seguidas para detectar dependencias de estado u orden.
- Ejecutar evaluaciones IA contra dataset versionado y comparar contra la línea base antes de aceptar cambios de prompt/modelo.
- Verificar que CI ejecuta lint, typecheck y tests en el pull request, con el mismo conjunto de comandos que local.
- Revisar salida de tests en busca de secretos, correos o fragmentos de CV.
- Confirmar que el reporte de fallo incluye `correlation_id` o identificador de ejecución para reproducirlo.

## Checklist

- [ ] Tests unitarios, integración y contract según el cambio.
- [ ] E2E del flujo de usuario cuando cambió el recorrido completo.
- [ ] Test cross-tenant explícito y en verde.
- [ ] Evaluación IA ejecutada si cambiaron prompt, modelo o workflow.
- [ ] Fidelidad de evidencia comprobada; ausencia marcada como tal.
- [ ] Sin proveedores pagos ni datos reales en tests.
- [ ] Lint, typecheck y tests ejecutados y reportados.
- [ ] Regression cubierta si había bug; CI configurada para correr lo mismo.

## Referencias

- `TalentOS_SDD.md` secciones 15.3, 16, 25 y criterios de ADR en 24.
- `TalentOS_ROADMAP.md` sección 3 (Fase 0) y sección 4 (lint, typecheck y tests en CI).
- `AGENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, `docs/ENVIRONMENTS.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: Playwright <https://playwright.dev/docs/intro>, Pydantic <https://docs.pydantic.dev/>, FastAPI <https://fastapi.tiangolo.com/>.
