# Inventario UI/UX — Entrega A (2026-11-25)

Fuente: `TalentOS_UI_UX_IMPROVEMENT_PLAN.md` §21–§24, `TalentOS_SDD.md`, `TalentOS_ROADMAP.md` y lectura directa del repositorio. A1 fue diagnóstico sin código; este inventario refleja A2 y A4 ya aplicados (ver §7). Sin commit/push.

## 1. Stack real

- `apps/web/package.json`: Next.js `16.4.6` (App Router), React `19.3.1`, React DOM `19.3.1`.
- TypeScript `5.9.3`, `tsconfig.json` con `strict: true`, `moduleResolution: "bundler"`, alias `@/*` → `./src/*`.
- Tailwind CSS `3.4.19` + PostCSS `8.5.33` + Autoprefixer `10.7.0`. `tailwind.config.ts` solo extiende colores, `fontFamily.sans`, radios y espaciado desde variables CSS; no define `screens`, por lo que usa breakpoints por defecto (`sm` 640, `md` 768, `lg` 1024, `xl` 1280, `2xl` 1536).
- Vitest `5.1.1` + Testing Library (DOM `10.4.2`, React `16.3.3`) + jsdom `31.0.1`; ESLint `9.39.5` con `eslint-config-next` `16.4.6`.
- `next.config.ts`: único ajuste `reactStrictMode: true`.
- `package.json` raíz: `npm run dev` = `docker compose up --build`.
- No hay `components.json`, `@radix-ui/*`, `lucide-react`, `class-variance-authority`, `tailwind-merge`, React Hook Form, Zod, TanStack Table, Recharts ni Sonner. `@playwright/test` `^1.65.1` ya está instalado como `devDependency` en `apps/web/package.json` y el script `test:e2e` = `playwright test` existe (ADR-015); `apps/web/playwright.config.ts` y `apps/web/e2e/smoke.spec.ts` ya existen.
- No existe `packages/contracts/`; contratos de la web se mantienen a mano en `apps/web/src/lib/types.ts`.

## 2. Rutas existentes

14 páginas en `apps/web/src/app/`, más `layout.tsx` y `error.tsx` globales. No hay `not-found.tsx`, `loading.tsx` ni layouts anidados. `layout.tsx` sigue intacto; el shell de workspace se monta de forma opt-in en cada una de las 14 rutas root vía `WorkspaceShell.tsx`.

| Ruta | Archivo | Contenido real | Dependencia API |
|---|---|---|---|
| `/` | `src/app/page.tsx` | Landing mínima: título, etiqueta «Fase 1 — Fundación del monorepo», CTA «Ir al panel» (antes «Panel», renombrado en A4 para no duplicar el shell) y enlaces a `/health` y `/ready` | Ninguna |
| `/login` | `src/app/login/page.tsx` + `LoginForm.tsx` | Formulario y enlace a `/register` | `POST /api/v1/auth/login` |
| `/register` | `src/app/register/page.tsx` + `RegisterForm.tsx` | Formulario y enlace a `/login` | `POST /api/v1/auth/register` |
| `/dashboard` | `src/app/dashboard/page.tsx` | Sesión, organización activa, miembros, navegación a 10 módulos; estados `loading`, `unauthorized`, `forbidden`, `error` | `GET /api/v1/auth/me`, organizaciones y miembros |
| `/jobs` | `src/app/jobs/page.tsx` + `JobsPanel`, `JobForm`, `RequirementsEditor` | Listado, formulario y requisitos | `/api/v1/jobs*` |
| `/candidates` | `src/app/candidates/page.tsx` + `CandidatesPanel`, `CandidateForm` | Listado, notas, actividad y alta | `/api/v1/candidates*` |
| `/applications` | `src/app/applications/page.tsx` + `PipelineBoard` | Pipeline por etapas y cambio de etapa | `/api/v1/applications*` |
| `/documents` | `src/app/documents/page.tsx` + `DocumentUpload`, `DocumentReview` | Subida, extracción y confirmación de campos | `/api/v1/documents*` |
| `/assessment` | `src/app/assessment/page.tsx` + `AssessmentPanel`, `AssessmentComparison`, `RequirementEvaluationCard` | Ejecución, comparación y revisión de evidencias | `/api/v1/assessment*` |
| `/agents` | `src/app/agents/page.tsx` + `AgentRunPanel`, `AgentEventTimeline`, `AgentApprovalControls` | Ejecuciones, eventos y aprobaciones | `/api/v1/agents*` |
| `/automations` | `src/app/automations/page.tsx` + `AutomationRulePanel`, `AutomationRunTimeline`, `AutomationNodeEditor`, `AutomationApprovalControls` | Reglas, versiones, ejecuciones y aprobaciones | `/api/v1/automations*` |
| `/integrations` | `src/app/integrations/page.tsx` + `IntegrationsPanel` | Proveedores, entregas y borradores de correo | `/api/v1/integrations*` |
| `/interviews` | `src/app/interviews/page.tsx` + `InterviewGuidePanel`, `QuestionEditor`, `GuideHistory`, `FeedbackForm` | Guías, preguntas, revisiones y feedback | `/api/v1/interviews*` |
| `/analytics` | `src/app/analytics/page.tsx` | Resumen, tabla y desgloses | `GET /api/v1/analytics/overview` |

Enlaces internos detectados: `/`, `/login`, `/register`, `/dashboard`, `/jobs`, `/candidates`, `/applications`, `/assessment`, `/documents`, `/agents`, `/automations`, `/integrations`, `/interviews`, `/analytics`. Todos apuntan a rutas existentes. No aparecen `/forgot-password`, `/reset-password` ni `/invite/[token]`.

## 3. Componentes, estilos y clientes

- `src/components/`: 28 componentes `.tsx` (incluye `WorkspaceShell.tsx`, shell opt-in con sidebar, header, breadcrumbs y nav móvil) y 2 tests inline (`IntegrationsPanel.test.tsx`, `RequirementEvaluationCard.test.tsx`). No hay carpeta `components/ui/`, `hooks/`, `features/` ni `services/`.
- `src/lib/api.ts`: cliente único `apiFetch<T>`. Lee `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`), envía `credentials: "include"`, añade `X-Organization-ID` desde `localStorage` (`talentos:active-org`) y parsea `ErrorEnvelope` (`code`, `message`, `request_id`) en `ApiError`. La sesión viaja en cookie HttpOnly; nunca se guarda un token en localStorage.
- `src/lib/types.ts`: 144 declaraciones exportadas (`interface` y `type`) de dominio. No hay generación desde esquema compartido.
- `QuestionEditor.tsx:28-31` redefine `API_BASE_URL` y en `QuestionEditor.tsx:81` usa `fetch` directo: segundo cliente HTTP con manejo de error propio (`QuestionRequestError`). Es el único desvío detectado respecto de `apiFetch`.
- `src/styles/tokens.css`: 11 colores (los 7 originales `surface`, `surface-muted`, `text`, `text-muted`, `border`, `accent`, `focus`, más `border-subtle`, `on-accent`, `success` y `warning` añadidos en A2), 2 variables de foco, 5 espacios, 2 radios y 1 pila tipográfica del sistema.
- `src/app/globals.css`: importa tokens, capas Tailwind, estilos base, `:focus-visible` con variables semánticas y bloque `prefers-reduced-motion`.
- `src/app/layout.tsx`: `lang="es"`, skip link `Saltar al contenido principal`, header mínimo con «TalentOS» y `main#main-content` con `tabIndex={-1}`.
- `src/app/error.tsx`: pantalla genérica de error con `role="alert"` y botón `Reintentar` (usa `reset` de Next).
- Los 28 usos de `text-white` sobre `bg-accent` se migraron a `text-on-accent` en A2; ya no quedan usos directos del color en clases.
- Hay 29 coincidencias de utilidades responsive/`overflow-x-auto`/`grid-cols-` en `src` (3 de ellas assertions en `IntegrationsPanel.test.tsx`). No hay navegación responsive real.
- `apps/web/tests/`: 15 archivos de test (añadido `workspace-shell.test.tsx`). Junto con los 2 tests inline suman 17 archivos / 97 tests, verdes en la última ejecución registrada; typecheck, lint y build también OK.

## 4. Contraste y paleta

Valores medidos en Fase 13 (`TalentOS_ROADMAP.md:679`): texto `15.65:1`, texto secundario `7.56:1`, acento `6.67:1`, bordes `3.67:1` sobre blanco y `3.36:1` sobre `surface-muted` (WCAG 1.4.11 para componentes).

| Plan §24 | Valor actual | Tratamiento propuesto |
|---|---|---|
| Primary `#18181B` | `--color-text: #1b2430` | Se mantiene el token actual; diferencia imperceptible y contraste ya verificado |
| Surface `#FAFAFA` | `--color-surface: #ffffff`, `--color-surface-muted: #f3f5f7` | Se mantienen; se puede añadir un token de superficie plana solo si un estado real lo pide |
| Border `#E4E4E7` | `--color-border: #7a8794` + `--color-border-subtle: #e4e4e7` (A2) | No sustituir el borde funcional: `#E4E4E7` no alcanza 3:1. El token subtle queda limitado a decoración |
| Muted text `#71717A` | `--color-text-muted: #4b5563` | Se mantiene: más contraste que el valor del plan |
| Success `#16A34A` | `--color-success: #166534` (A2) | Token añadido; contraste verificado |
| Warning `#D97706` | `--color-warning: #92400e` (A2) | Token añadido; contraste verificado |

## 5. Gaps respecto del plan

1. **Rutas:** las 14 existen, pero el plan habla de `/app/*`. Migrar rompería enlaces y tests sin capacidad nueva. No se hace sin ADR explícito.
2. **Landing:** `src/app/page.tsx` es una lista de enlaces con etiqueta de fase; no comunica producto, no jerarquiza CTAs y no tiene secciones.
3. **Workspace:** A4 añade `WorkspaceShell.tsx` opt-in en las 14 rutas root (sidebar, header, breadcrumbs, nav móvil con `aria-expanded`/`aria-controls`, prop `section`); `layout.tsx` global sigue mínimo. Siguen ausentes command menu, menú de usuario y selector de organización persistente.
4. **Estados globales:** no hay `not-found.tsx`, no hay `loading.tsx`, no hay 401/403/500 diferenciados por ruta. Solo `error.tsx` genérico y los estados locales de `/dashboard`.
5. **Componentes:** no hay primitives compartidas (A3 pendiente). Patrones de botón, campo, tabla y tarjeta se repiten en 28 componentes; las 28 clases `text-white` ya se migraron a `text-on-accent` en A2.
6. **Doble cliente HTTP:** `QuestionEditor.tsx` evade `apiFetch`; cualquier cambio de contrato de error o de cabecera debe hacerse en dos sitios.
7. **shadcn/ui:** el plan lo exige en Entrega A, pero no hay `components.json`, dependencias Radix ni justificación de mantenimiento/compatibilidad. Su adopción requiere una ADR específica —ADR-015 cubre E2E, no UI—; agregarlo ahora duplicaría componentes existentes y violaría `AGENTS.md` («no introducir dependencias sin justificación documentada»).
8. **Responsive:** hay grillas y tablas con desbordamiento; A4 añadió nav móvil opt-in en `WorkspaceShell.tsx`, pero no hay revisión exhaustiva en dispositivos ni verificación desktop/móvil. La Fase 13 sigue `IN_PROGRESS` por este motivo (`TalentOS_ROADMAP.md:681`).
9. **E2E (A5, en curso):** framework decidido en ADR-002 y dependencia `@playwright/test` `^1.65.1` instalada con script `test:e2e`; `apps/web/playwright.config.ts` (con `WEB_BASE_URL`, default `http://localhost:3000`) y `apps/web/e2e/smoke.spec.ts` ya existen, y el smoke añade asserts desktop+móvil. `.github/workflows/ci.yml` tiene el paso E2E tras `Build` con `npx playwright install --with-deps chromium` y `cd apps/web && npm run test:e2e`. El criterio de salida de Fase 13 no está verificado; ver ADR-015. No marcar DONE.
10. **Datos mock:** la web consume API real; no hay identificadores visuales de modo demo en ninguna pantalla. No se introduce uno sin contrato backend.
11. **Formularios:** estados de error accesibles ya implementados en login, registro y feedback (`Error:` + `role="alert"`), pero sin patrón unificado ni auditoría del resto.

## 6. Riesgos de regresión

- `layout.tsx` no se tocó en A4: skip link y `main#main-content` permanecen. El shell se monta por ruta; cambiarlo exige revisar las 14 rutas y el test `workspace-shell.test.tsx`.
- Renombrar rutas rompe enlaces en `page.tsx`, `dashboard`, `login`, `register` y tests, además de las anclas `/dashboard#...` del shell. La home usa «Ir al panel» para no duplicar el acceso del shell.
- Cambiar `tokens.css` altera `surface`, `text`, `border` y `accent` en toda la app: cualquier cambio pasa por verificación de contraste.
- Sustituir `border` por `#E4E4E7` degradaría cumplimiento WCAG 1.4.11.
- Instalar shadcn/Radix sin ADR específica añade dependencias y puede duplicar componentes actuales (ADR-015 es de E2E y no habilita UI).
- Unificar `QuestionEditor` a `apiFetch` cambia el contrato de errores de esa pantalla: requiere tests.
- Declarar Entrega A como `DONE` sin cerrar E2E y responsive contradice `TalentOS_ROADMAP.md:681`.

## 7. Lotes propuestos para la Entrega A

| Lote | Alcance | Estado |
|---|---|---|
| A1 | Lectura de SDD/ROADMAP/plan, inventario de stack, rutas, componentes, API y gaps; ADR-014 | Completado sin código |
| A2 | Ampliar `tokens.css` + `tailwind.config.ts` con success/warning/focus/subtle y token para texto sobre acento; sin hex en componentes | Completado: `text-on-accent` en 28 usos, success `#166534`, warning `#92400e`, borde subtle decorativo |
| A3 | Primitivas accesibles propias (`Button`, `Field`, `Input`, `Table`, `Card`) sobre Tailwind + ARIA, migración incremental | Pendiente de OK explícito; shadcn/ui requiere ADR propia (ADR-015 es de E2E) |
| A4 | Shell de workspace opt-in (sidebar, header, breadcrumbs, nav móvil) sin mover rutas ni reemplazar `layout.tsx` global | Completado: `WorkspaceShell.tsx` en las 14 rutas root, test `tests/workspace-shell.test.tsx`, anclas `/dashboard#...`; commit `fa8e6d9` |
| A5 | `not-found.tsx`, `loading.tsx`, diferenciación 401/403/500 y smoke E2E | **En curso** (ADR-015): config con `WEB_BASE_URL` (default `http://localhost:3000`), smoke con asserts desktop+móvil creado; E2E local 3 pasan / 1 skip. `.github/workflows/ci.yml` tiene E2E tras `Build` con `npx playwright install --with-deps chromium`. Smoke responsive verificado en local y CI (3 passed / 1 skipped; run `45696148206`, headSha `fa8e6d9`); pendiente revisión en dispositivos reales. No marcar DONE |

Cada lote se cierra con `npx tsc --noEmit`, `npm run lint`, `npm test -- --run` y `npm run build` en `apps/web`; A5 añade el paso E2E en `.github/workflows/ci.yml` tras `Build`, con `npx playwright install --with-deps chromium` y `cd apps/web && npm run test:e2e` (ADR-015). Tras A4: typecheck, lint y build OK; 17 archivos / 97 tests verdes. Commit `fa8e6d9` pusheado. **Entrega A sigue `IN_PROGRESS`**: A3 pendiente de OK explícito; A5 con smoke E2E verificado en local y CI (asserts desktop+móvil), dispositivos reales pendientes; no se marca `DONE` hasta cerrar Fase 13 o documentar explícitamente su alcance parcial.
