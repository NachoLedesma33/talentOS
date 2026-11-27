# TalentOS — Revisión de seguridad y privacidad (Fase 14)

Estado: 2026-11-27. Alcance evaluado: repositorio en modo `local`/`test` con datos sintéticos. No constituye asesoramiento legal. Evidencia de CI: dependencias `45880065546`, cabeceras y HTTPS `45915102956`, rate limit de autenticación `45919600293`, esquemas estrictos `45922837838`, límite de tamaño `45925962276`, eventos de seguridad `45929163932`, CSRF `45932408840` y `45933203449`; todos success.

## Threat model mínimo

- **Activos:** credenciales y sesiones, CV/documentos, evidencia de evaluación, secretos de integraciones, logs estructurados.
- **Actores:** anónimo, `viewer`/`reviewer`/`recruiter`/`admin`/`owner`, worker Celery, proveedor LLM configurable, webhook entrante.
- **Fronteras de confianza:**
  1. `request` → `get_current_user` (`apps/api/app/identity/dependencies.py:47`): cookie de sesión opaca, hash SHA-256, expiración y revocación.
  2. `X-Organization-ID` → `get_current_organization` (`:74`): UUID validado contra membresía real; nunca se confía en el header sin verificación.
  3. Rol → `require_roles` (`:104`): autorización por recurso y acción, no solo por ruta.
  4. Dominio → repositorio: cada consulta filtra por `organization_id` de la sesión autorizada.
  5. Dominio → storage/worker/proveedor: claves por organización y documento, tools con contrato Pydantic y salidas validadas.
  6. Respuesta/logs: metadatos controlados; sin payload de CV, tokens ni chain-of-thought.

Flujo crítico: `cookie + X-Organization-ID` → sesión → membresía → rol → servicio tenant-scoped → repositorio → storage privado. Webhook: HMAC + timestamp + dedupe antes de tocar dominio. LLM: texto del documento tratado como dato, nunca como instrucción.

## Checklist de revisión

| Ítem | Resultado | Evidencia / riesgo |
|---|---|---|
| Threat model actualizado | Revisado | Sección anterior; decisiones en `docs/decisions/ADR-017.md`. |
| Matriz de roles y permisos revisada | Revisado | `apps/api/app/identity/dependencies.py:1-12,104-118`; tests en `apps/api/tests/test_authorization.py`. |
| Tests cross-tenant completos | Revisado | `apps/api/tests/test_authorization.py` y `test_*_api.py` con dos organizaciones sintéticas; 530 tests en verde. |
| Autenticación y sesiones | Revisado | bcrypt + límite 72 bytes (`identity/security.py`); token opaco con hash SHA-256; `HttpOnly`, `SameSite=lax`, `Secure` en producción (`api/routes/auth.py:87-95`). |
| Esquemas de entrada | Revisado | `extra=forbid` en `identity/schemas.py:13-14,67-69,90-92` para registro, login, organización, invitación y reset; tests en `tests/test_auth.py`. |
| CORS y CSRF | Revisado | Origen web explícito sin comodín (`app/main.py:46-53`); `verify_origin` exige `Origin` en mutaciones bajo `staging`/`production` y valida esquema/host/puerto (`identity/dependencies.py:37-38,134-152`); `SameSite=lax`. |
| Cabeceras y transporte | Revisado | `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` en toda respuesta (`app/main.py:107-112`); CSP y HSTS en producción; redirect 307 HTTP→HTTPS con `X-Forwarded-Proto` (`app/main.py:114-130`); docs deshabilitados en producción (`app/main.py:37-44`); tests en `test_health.py`. |
| Rate limiting | Parcial | Límite por tool de agente (`agents/tools.py:641`) y 60 intentos/minuto por IP en `login`, `forgot-password` y `reset-password` bajo `staging`/`production` (`app/main.py:70-80,161-184`); 429 con `Retry-After`. Sin límite global HTTP: riesgo `RM-01`. |
| Upload y parsing | Revisado | Extensión, MIME declarado, firma real, 10 MiB y 50 páginas (`documents/validation.py:8-14,50-71`); parseo determinista sin servicio externo. Límite global de 2 MiB para cuerpo no multipart con 413 uniforme (`app/main.py:68-69,132-160`); multipart queda bajo la cota específica de upload. |
| Storage y URLs firmadas | Revisado | Storage privado por UUID (`documents/storage.py`); token HMAC-SHA256 con `exp` y tenant, TTL 60 s (`documents/tokens.py`). Clave efímera por proceso: riesgo `RM-02`. |
| Secretos y cifrado | Revisado | Configuración solo desde entorno (`core/config.py`); Fernet por organización (ADR-013); `.env.example` sin valores secretos. HTTPS/HSTS aplicados por API en producción; cifrado de reposo gestionado en despliegue: riesgo `RM-03`. |
| Prompt injection | Revisado | Contratos de salida y detección en `agents/cv_analyst.py`; tests en `apps/api/tests/test_cv_analyst.py:337-352` y `test_documents_review.py:424-469`. |
| Herramientas de agentes | Revisado | Permisos, timeout, idempotencia y aprobación humana en `agents/tools.py:145-152,504-554,622-673`. |
| Webhooks | Revisado | HMAC-SHA256 en tiempo constante, anti-replay y dedupe por organización (`integrations/webhooks.py:130-142,202`); tests en `test_inbound_webhooks.py`. |
| Logs y datos personales | Revisado | `JsonFormatter` solo metadatos (`core/logging.py:12-24`); eventos `auth_login_failed` y `auth_password_reset_failed` con `request_id`/`correlation_id` (`api/routes/auth.py:43-51,82,123`); tests de redacción en `test_documents_tasks.py`, `test_email_sandbox.py`, `test_inbound_webhooks.py` y `test_auth.py`. |
| Retención y eliminación | Parcial | Purga de eventos de agente a 30 días (`agents/tasks.py:150-180`). Sin exportación/eliminación de candidatos: riesgo `RM-04`. |
| Escaneo de dependencias | Revisado | `npm audit --audit-level=high` y `pip-audit` en CI con venv aislada; `cryptography` subido a `>=50,<51`. |
| Backup y restauración | Pendiente | Sin procedimiento automatizado: riesgo `RM-05`. |
| Checklist OWASP aplicable | Revisado | ASVS V2/V3/V4/V5/V6/V8/V10/V12/V14 cubiertos por controles anteriores; brechas en `RM-01`, `RM-03`, `RM-05`. |
| Documentación de riesgos pendientes | Revisado | Sección siguiente; aceptación explícita solo para alcance demo/local. |

## Riesgos residuales

| ID | Riesgo | Mitigación actual | Condición antes de producción |
|---|---|---|---|
| `RM-01` | Sin rate limiting global HTTP. | Sesión cookie, CSRF por `Origin`, límites en tools y en autenticación desplegada. | Limiter por IP/usuario/organización respaldado por Redis en el resto de endpoints sensibles. |
| `RM-02` | Clave de URLs firmadas efímera por proceso. | TTL 60 s y firma tenant-scoped. | Clave estable por despliegue desde gestor de secretos para múltiples réplicas. |
| `RM-03` | Cifrado de reposo depende de infraestructura. | Fernet para secretos de integración; sin secretos en repo; HTTPS 307 + HSTS en producción (`app/main.py:111-127`). | Verificar cifrado gestionado de PostgreSQL/storage en staging. |
| `RM-04` | Sin exportación/eliminación configurable de datos de candidato. | Datos sintéticos en `local`/`test`; acceso por rol y tenant. | Política de retención, consentimiento y flujo de borrado/exportación con registro. |
| `RM-05` | Backup y restauración no probados. | Migraciones versionadas con Alembic. | Backup programado y restauración verificada en staging con plan de rollback. |

Aceptación: riesgos `RM-01`–`RM-05` se aceptan explícitamente para el alcance demo/local de Fase 14 porque no hay datos personales reales ni despliegue público. Fase 15 debe cerrarlos o documentar una aceptación nueva firmada antes de manejar candidatos reales.
