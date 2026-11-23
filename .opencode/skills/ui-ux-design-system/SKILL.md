---
name: ui-ux-design-system
description: Aplica el sistema visual B2B de TalentOS, tokens, jerarquía, estados y accesibilidad al crear o revisar pantallas, con evidencia legible y aprobación humana explícita.
---

# UI/UX Design System — TalentOS

## Objetivo
Mantener una interfaz profesional, sobria y orientada a datos para reclutamiento, con tokens y componentes consistentes. El sistema visual debe ayudar a interpretar evidencias y decisiones humanas, no decorarlas ni ocultar incertidumbre.

## Cuándo activarla
- Al diseñar o revisar cualquier pantalla del MVP listada en `TalentOS_SDD.md` §13.3.
- Al definir tokens de color, tipografía, espaciado, radios, sombras, iconografía o estados.
- Al revisar tablas densas, timelines de agentes, vistas de evidencia o formularios de aprobación.
- Al detectar inconsistencias entre componentes, contraste insuficiente o estilos experimentales.
- No activar para decidir reglas de negocio, permisos o contratos API: eso pertenece a backend.

## Contexto TalentOS
- Dirección visual: B2B SaaS profesional, responsive, navegación lateral persistente en desktop, tablas densas pero legibles, contraste accesible y animaciones discretas (SDD §13.1).
- Prohibido estéticamente: abusar de gradientes, glassmorphism o tarjetas decorativas; priorizar claridad operativa.
- Jerarquía de navegación definida: Overview → Vacantes → Candidatos → Pipeline → Entrevistas → Automatizaciones → AI Agents → Simulation Lab → Analytics → Configuración.
- Candidate Assessment: requisitos a la izquierda; estado, evidencia y fragmento fuente por requisito; brechas, preguntas y acciones de revisión a la derecha (SDD §13.3).
- Agent Control Center: timeline de nodos, herramientas invocadas, duración, errores, reintentos, aprobaciones pendientes y uso estimado del modelo.
- Estados semánticos a representar visualmente: `supported`, `partial`, `not_found`, `needs_review`; estados de ejecución `pending`, `running`, `waiting_approval`, `completed`, `failed`, `cancelled`, `timed_out`.
- Multi-tenancy: la organización activa puede mostrarse como contexto, pero nunca como control editable que cambie el alcance sin validación del backend.
- Human-in-the-loop: aprobación/rechazo son acciones explícitas, con consecuencia y actor visibles; ningún color o icono debe sugerir que la IA decidió sola.
- Evidencias: la cita debe incluir documento, página y fragmento; la ausencia de evidencia se representa de forma inequívoca, no con un espacio vacío.
- Modo mock: patrones y capturas usan candidatos sintéticos; sin CVs reales ni datos personales en el design system.
- Sin secretos en tokens, capturas, ejemplos de código ni configuración visual.

## Procedimiento
1. Leer `TalentOS_SDD.md` §13, §1.2 y §14.4; revisar la pantalla en `TalentOS_ROADMAP.md` según la fase activa; leer `AGENTS.md`.
2. Identificar la decisión que el usuario debe tomar en la pantalla y qué información necesita para tomarla: requisito, evidencia, brecha, limitación y actor.
3. Seleccionar tokens existentes en `apps/web/src/styles/`; si falta un token, agregarlo con nombre semántico y documentar su uso, sin duplicar valores hexadecimales en componentes.
4. Definir jerarquía: título, resumen, acción principal, datos de detalle; una sola acción principal por vista cuando sea posible.
5. Diseñar tablas y listas para escaneo: alineación consistente, estados compactos, truncation controlada y texto completo accesible mediante título o detalle.
6. Representar cada estado semántico con color + etiqueta + forma/icono, nunca solo color; verificar contraste y lectura en modo claro/oscuro si ambos existen.
7. Aplicar los ocho estados de interfaz de SDD §13.4: carga, vacío con acción, error accionable, éxito, deshabilitado, permisos insuficientes, confirmación destructiva e indicador de proceso asíncrono.
8. Revisar foco, teclado, lectores de pantalla y mensajes de estado; la evidencia y las aprobaciones deben ser comprensibles sin ver la pantalla.
9. Verificar que la vista no inventa evidencia: textos de ejemplo son ficticios y `needs_review` conserva su significado.
10. Registrar la revisión con captura de datos sintéticos y resultado de checks de UI; actualizar tokens/docs si el cambio es reutilizable.

## Convenciones
- Tokens semánticos primero (`status.supported`, `status.needs_review`, `surface.muted`); valores crudos solo en la definición del token.
- Tipografía sobria y jerárquica; números y fechas alineados en tablas; fechas mostradas en zona del usuario, almacenadas en UTC.
- Los iconos acompañan, no sustituyen etiquetas; estados con significado distinto no comparten solo matiz de color.
- Espaciado consistente entre secciones, formularios y tablas; densidad alta sin sacrificar área de clic ni foco visible.
- Multi-tenancy: el contexto organizacional se muestra como dato de sesión, no como fuente de autorización.
- HITL: botones de aprobación con etiqueta concreta (“Aprobar envío”, “Rechazar y devolver a revisión”), nunca “Aceptar” ambiguo.
- Evidencia: fragmento fuente, página y documento siempre visibles o accesibles en un paso; `not_found` y `needs_review` tienen texto propio.
- Modo mock: estados de demostración provienen de fixtures sintéticas y se reinician sin datos reales.
- Secretos y datos personales: ningún token, CV, correo o nombre real en capturas, historias de diseño ni ejemplos.
- Movimiento: solo transiciones funcionales y breves; respetar preferencias de movimiento reducido.

## Anti-patrones
- Interfaz “de producto IA” con rankings opacos, puntajes sin criterio o confianza presentada como verdad.
- Ocultar brechas o datos faltantes para que la evaluación parezca completa.
- Representar estados solo por color, con contraste bajo o sin etiqueta para lectores de pantalla.
- Mezclar estilos heredados, gradients llamativos, tarjetas decorativas o animaciones que distrajan de la tarea.
- Mostrar una aprobación como automática o eliminar la confirmación de acciones destructivas.
- Insertar organizaciones, candidatos o CVs reales en capturas y mocks visuales.
- Usar valores de color/espaciado duplicados en componentes en vez de tokens.
- Copiar patrones de diseño de otras aplicaciones sin verificar que cubren los estados obligatorios del SDD.

## Validación
- Revisión visual de las pantallas afectadas contra §13.1 y §13.4, con datos sintéticos.
- Comprobar que `supported`, `partial`, `not_found` y `needs_review` se distinguen por texto y forma, no solo color.
- Recorrido por teclado y lector de pantalla de la vista de evidencia y del flujo de aprobación.
- Capturas sin secretos, correos reales, nombres reales ni contenido de CV real.
- E2E del flujo crítico cuando corresponda: `npx playwright test`; unitarios de componentes: `cd apps/web && npm test -- --run`.
- Gates de frontend: `cd apps/web && npx tsc --noEmit` y `cd apps/web && npm run lint`.
- En Fase 0 no hay UI: validar esta skill por relectura y contraste conceptual con SDD §13; no generar pantallas ni dependencias visuales.

## Checklist
- [ ] Pantalla revisada contra dirección visual y navegación del SDD.
- [ ] Tokens semánticos usados; sin valores duplicados.
- [ ] Ocho estados de interfaz presentes donde aplica.
- [ ] Estados de evidencia y ejecución distinguibles sin depender del color.
- [ ] Evidencia con documento, página y fragmento, o `needs_review` explícito.
- [ ] Aprobación humana explícita, con actor y consecuencia visibles.
- [ ] Accesibilidad por teclado, foco, etiquetas y contraste comprobada.
- [ ] Capturas y mocks con datos sintéticos; sin secretos.
- [ ] Checks de UI ejecutados y evidencia adjunta.

## Referencias
- `TalentOS_SDD.md`: §1.2, §3.3, §9.5, §13, §14.4, §16 y §20.
- `TalentOS_ROADMAP.md`: §3 (Fase 0, sin UI) y fases que entregan cada pantalla del MVP.
- `AGENTS.md`: stack frontend, Definition of Done y prohibición de secretos/datos personales.
- `docs/decisions/`: ADR-002 (stack) y decisiones de producto que afecten la información visible.
- `docs/DEVELOPMENT_WORKFLOW.md`: evidencia para `DONE` y requisitos de E2E en flujos críticos.
- `docs/ENVIRONMENTS.md`: entornos de demo/test y variables sin secretos.
- Documentación oficial citada en `TalentOS_SDD.md` §26: Next.js (https://nextjs.org/docs), Playwright (https://playwright.dev/docs/intro) y OWASP ASVS (https://owasp.org/www-project-application-security-verification-standard/).
