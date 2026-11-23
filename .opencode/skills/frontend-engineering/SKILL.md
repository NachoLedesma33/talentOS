---
name: frontend-engineering
description: Implementa pantallas y componentes Next.js/TypeScript de TalentOS con contratos tipados, estados UI completos, accesibilidad y backend como autoridad.
---

# Frontend Engineering — TalentOS

## Objetivo
Construir la web de TalentOS en `apps/web` con Next.js + TypeScript, consumiendo solo la API `/api/v1`, con estados de interfaz completos y sin duplicar reglas de negocio. El frontend debe hacer visible la evidencia y la aprobación humana, no simularlas.

## Cuándo activarla
- Al crear o modificar rutas en `apps/web/src/app/`, componentes en `components/`, features en `features/`, hooks, servicios o estilos.
- Al conectar una pantalla con endpoints de la API o con contratos de `packages/contracts/`.
- Al añadir estados de carga, vacío, error, deshabilitado, permisos insuficientes o confirmación.
- Al revisar accesibilidad, navegación por teclado o responsive de una vista existente.
- No activar para cambios de esquema, endpoints o reglas de autorización: esos se resuelven en backend y luego se consumen.

## Contexto TalentOS
- Stack: Next.js + TypeScript, Tailwind CSS y componentes accesibles (SDD §6.2); librería visual común en `src/styles/` y componentes reutilizables en `src/components/`.
- Estructura prevista: `app`, `components`, `features`, `hooks`, `lib`, `services`, `styles` dentro de `apps/web/src/`, con tests en `apps/web/tests/` (SDD §7).
- Backend como autoridad: la web no calcula permisos, no decide si un candidato es adecuado y nunca accede a PostgreSQL ni a storage directamente.
- Navegación del MVP: Overview, Vacantes, Candidatos, Pipeline, Entrevistas, Automatizaciones, AI Agents, Simulation Lab, Analytics, Configuración (SDD §13.2).
- Pantallas críticas: Candidate Assessment con requisitos a la izquierda, evidencia y fragmentos fuente a la derecha; Agent Control Center con timeline, tools, errores y aprobaciones (SDD §13.3).
- Contratos: usar tipos compartidos de `packages/contracts/` cuando existan; si no, definir el tipo local y proponer su publicación, sin inventar el endpoint.
- Multi-tenancy: la organización activa viene de la sesión; la UI no ofrece un selector que permita ver otra organización sin validación del backend.
- Human-in-the-loop: botones de aprobar/rechazar son propuestas; el estado final lo devuelve la API tras verificar rol y organización.
- Evidencias: mostrar `quote`, `page` y `document_id` de cada `evidence_refs`; `not_found` y `needs_review` deben verse distintos de `supported`.
- Modo demo: datos sintéticos y `LLM_PROVIDER=mock`; ninguna pantalla depende de una clave de proveedor ni muestra secretos en DevTools.
- Sin datos personales reales en fixtures ni capturas; los CVs de ejemplo son ficticios.

## Procedimiento
1. Leer el RF y criterios en `TalentOS_SDD.md` §4, la vista en §13, `AGENTS.md` y la fase activa de `TalentOS_ROADMAP.md`.
2. Confirmar que el contrato API existe y está tipado; si falta, coordinar con backend antes de crear un tipo ad-hoc definitivo.
3. Implementar la unidad en la carpeta correcta: página/ruta en `app/`, lógica de pantalla en `features/`, piezas reutilizables en `components/`, acceso HTTP en `services/`.
4. Llamar a la API desde un servicio con manejo de `request_id`, errores y timeouts; no exponer URLs ni secretos de servidor al cliente.
5. Renderizar los ocho estados obligatorios de SDD §13.4 para cada vista: loading/skeleton, empty, error accionable, success, disabled, permisos insuficientes, confirmación destructiva e indicador de proceso asíncrono.
6. En vistas de IA, mostrar entrada analizada, criterios evaluados, evidencia con referencia verificable, brechas, limitaciones y quién aprobó la acción.
7. En acciones sensibles, enviar la decisión a la API y reflejar el estado devuelto; nunca optimizar la aprobación como cambio local definitivo.
8. Asegurar accesibilidad: etiquetas asociadas, foco visible, navegación por teclado, roles ARIA correctos, contraste suficiente y anuncios de estado para procesos largos.
9. Evitar refetch cross-tenant: claves de caché y store incluyen la organización activa; limpiar datos al cambiar de organización o cerrar sesión.
10. Ejecutar typecheck, lint, unitarios y E2E del flujo crítico; adjuntar comandos, salida y captura sin datos personales.

## Convenciones
- TypeScript estricto; sin `any` para respuestas de API; los enums de estado vienen del contrato compartido.
- Componentes pequeños y deterministas: props explícitas, sin lectura directa de sesión dentro de piezas presentacionales.
- Servicios HTTP centralizados en `services/`: una función por operación, con tipado de entrada/salida y errores uniformes.
- Contraseñas, tokens y API keys jamás en `NEXT_PUBLIC_*`, localStorage, logs de navegador ni mensajes de error.
- Multi-tenancy: ninguna petición construye `organization_id` desde la URL para autorizarse; el backend valida membresía.
- HITL: toda aprobación tiene confirmación, registro visible de actor y estado `waiting_approval`/`completed`/`rejected` devuelto por API.
- Evidencia: cita sin `document_id` o `page` se muestra como no verificable; no se inventa texto para rellenar la UI.
- Modo mock: las fixtures de demo son candidatos sintéticos con nombres y correos ficticios; se pueden reiniciar sin tocar datos reales.
- Animaciones discretas y funcionales; respetar `prefers-reduced-motion` cuando aplique.
- Logs de navegador sin CV completo, email real ni token; para diagnosticar usar `correlation_id`.

## Anti-patrones
- Calcular roles, permisos o recomendaciones de candidatos en el cliente.
- Consumir un endpoint distinto del documentado o inventar campos que el backend no devuelve.
- Mostrar una evaluación de matching sin criterios, evidencia y limitaciones; ocultar `needs_review` para que el flujo parezca exitoso.
- Autoaprobar acciones externas o cambiar una decisión humana desde optimismo local.
- Dejar vista sin empty/error/loading: el usuario no puede distinguir “sin datos” de “falló la carga”.
- Hardcodear credenciales, URLs privadas, correos reales o fragmentos de CV reales en componentes o tests.
- Mezclar estilos de diferentes sistemas visuales o abusar de gradientes, glassmorphism y tarjetas decorativas (SDD §13.1).
- Desactivar lint, typecheck o tests para cerrar una tarea.

## Validación
- Unitarios de componentes con props de ejemplo sintéticos: estados loading/empty/error/success y respuestas 403/404.
- Integración del servicio HTTP con mock: verificar ruta `/api/v1`, payload, `request_id`, manejo de timeout y errores.
- E2E con Playwright para flujos críticos: revisar evidencia, aprobar acción, cambiar de organización sin fuga de datos.
- Accesibilidad: recorrido completo por teclado, foco visible, etiquetas y anuncios de estado; contraste verificado en estados de evidencia y error.
- Sin secretos ni datos personales reales en capturas, snapshots ni fixtures.
- Gates: `cd apps/web && npx tsc --noEmit`, `cd apps/web && npm run lint`, `cd apps/web && npm test -- --run`, `npx playwright test`.
- En Fase 0 no existen estas carpetas: la validación es la relectura de la skill y sus referencias; no ejecutar comandos de código inexistente.

## Checklist
- [ ] Rutas y componentes creados en las carpetas previstas de `apps/web`.
- [ ] Contratos tipados y consumo exclusivo de API `/api/v1`.
- [ ] Ocho estados de interfaz contemplados en la vista.
- [ ] Evidencia, brechas y limitaciones visibles cuando aplica.
- [ ] Aprobación humana enviada a backend y reflejada desde su respuesta.
- [ ] Multi-tenancy y permisos insuficientes probados; sin caché cross-tenant.
- [ ] Accesibilidad por teclado, foco, etiquetas y contraste revisada.
- [ ] Modo mock con datos sintéticos; sin secretos ni CVs reales.
- [ ] Typecheck, lint, unitarios y E2E ejecutados con evidencia real.

## Referencias
- `TalentOS_SDD.md`: §3.2, §4.4, §6.4, §7, §9.5, §12, §13, §16 y §25.
- `TalentOS_ROADMAP.md`: §3 (Fase 0), §4 (Fase 1, web) y fases funcionales de la vista.
- `AGENTS.md`: backend como autoridad, multi-tenancy, comandos de validación y reglas de secretos/datos.
- `docs/decisions/`: ADR-002 (stack) y decisiones que afecten contratos compartidos.
- `docs/DEVELOPMENT_WORKFLOW.md`: plantilla de tarea, estados y evidencia obligatoria.
- `docs/ENVIRONMENTS.md`: puertos locales, `LLM_PROVIDER=mock` y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: Next.js (https://nextjs.org/docs), Playwright (https://playwright.dev/docs/intro) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
