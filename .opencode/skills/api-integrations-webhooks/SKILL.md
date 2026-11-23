---
name: api-integrations-webhooks
description: Implementa adaptadores de proveedores y webhooks de TalentOS con firma HMAC anti-replay, deduplicación por organización, idempotencia, reintentos y evidencia de entrega.
---

# API Integrations y Webhooks — TalentOS

## Objetivo

Integrar servicios externos sin filtrar datos de candidatos, sin duplicar efectos y sin permitir que un payload externo altere el tenant equivocado. Todo evento debe poder verificarse, deduplicarse, reintentarse y diagnosticarse.

## Cuándo activarla

- Agregar o cambiar un adaptador de proveedor (ATS, calendario, correo, storage, LLM).
- Recibir o emitir webhooks.
- Modificar reintentos, timeouts, colas, outbox o estados de entrega.
- Exponer configuración de integración por organización.
- Depurar eventos duplicados, perdidos o aplicados a otra organización.

## Contexto TalentOS

- TalentOS es multi-tenant: `organization_id` es parte de la identidad del evento, no un dato opcional del payload.
- El SDD define eventos con `organization_id`, `occurred_at`, `resource_id`, `correlation_id` y `payload_version` (sección 11.1).
- Los clientes de proveedor viven en `apps/api/app/integrations/`; el procesamiento asíncrono en `apps/api/app/workers/`; los contratos compartidos en `packages/contracts/`.
- El aislamiento y la autorización se validan en backend; la UI nunca es la barrera de seguridad.
- Los secretos de integración se leen de variables de entorno o gestor de secretos; `.env.example` solo declara nombres.
- Los resultados de IA y las automatizaciones deben ser trazables y revisables por una persona; ningún webhook decide contrataciones.

## Procedimiento

1. Leer `TalentOS_SDD.md` secciones 11, 14, 15 y 25, `AGENTS.md`, `TalentOS_ROADMAP.md` sección 3 y `docs/DEVELOPMENT_WORKFLOW.md`.
2. Definir el contrato del evento en `packages/contracts/` con Pydantic: versión, identificador externo, tenant, recurso, timestamp UTC y correlación. No aceptar campos libres sin validar.
3. Resolver el tenant desde la configuración verificada de la integración o la sesión autenticada. Nunca confiar en un `organization_id` enviado por el proveedor sin validación.
4. Para webhooks entrantes: verificar firma HMAC sobre el cuerpo crudo, comparar en tiempo constante y rechazar cuerpo modificado.
5. Validar `timestamp` con tolerancia anti-replay configurable (por defecto 300 s) y rechazar eventos futuros o expirados.
6. Persistir el evento con restricción única `(organization_id, proveedor, event_id)`; si ya existe, responder éxito sin reprocesar.
7. Responder `2xx` después de verificar, deduplicar y encolar; hacer el trabajo real en background con `correlation_id` propagado.
8. Para webhooks salientes: firmar con HMAC, enviar `key_id` para rotación, guardar secreto por organización y registrar intentos, respuesta y estado final.
9. Usar transactional outbox cuando el evento y la transacción de dominio deban persistir juntos.
10. Aplicar reintentos exponenciales con máximo definido, timeout por proveedor y dead-letter o registro de tareas fallidas; permitir reintento manual con permisos.
11. Excluir CV completos, tokens y datos personales innecesarios del payload y de los logs; registrar solo IDs, hashes y metadatos.
12. Actualizar contratos, tests y documentación operativa en el mismo cambio; si cambia el protocolo, proponer ADR en `docs/decisions/`.

## Convenciones

- Un adaptador por proveedor con interfaz interna estable; la lógica de negocio no importa SDKs externos directamente.
- `event_id` inmutable y opaco; el dedupe se guarda con llave única en PostgreSQL.
- HMAC-SHA-256 con secreto rotatorio por organización; durante la rotación se acepta solo la versión anterior dentro de una ventana documentada.
- Timestamps en ISO 8601 UTC; reloj del servidor como referencia para la tolerancia.
- Errores tipados: `invalid_signature`, `stale_event`, `duplicate_event`, `provider_timeout`, `provider_rejected`.
- `correlation_id` viaja de request a worker y a logs; estado visible para el usuario en cada entrega.
- Payload versionado; cambios incompatibles requieren nueva versión y consumidores actualizados.

## Anti-patrones

- Confiar en headers de tenant, firmas opcionales o timestamps del proveedor sin validarlos.
- Guardar API keys en código, fixtures, logs, mensajes de error o capturas de trazas.
- Publicar el CV completo o datos de contacto en un webhook saliente “para que el proveedor lo tenga todo”.
- Reintentar sin idempotencia ni límite; provocar loops entre automatizaciones.
- Procesar el webhook en la request y responder solo al terminar, generando timeouts y reenvíos.
- Borrar el registro fallido para “limpiar” la cola sin dejar evidencia.
- Reutilizar un único secreto global entre organizaciones o entornos.

## Validación

- Ejecutar `cd apps/api && python -m ruff check .`, `cd apps/api && python -m mypy app` y `cd apps/api && python -m pytest -q`; registrar comandos y resultado real según `docs/DEVELOPMENT_WORKFLOW.md`.
- En Fase 0, donde `apps/api` aún no existe, la validación es la relectura de este archivo y el chequeo de rutas citadas.
- Tests de firma válida, firma inválida, cuerpo modificado, `key_id` desconocido y rotación de secreto.
- Tests de timestamp expirado y futuro dentro/fuera de tolerancia.
- Test de replay: mismo `event_id` dos veces produce un solo efecto.
- Test cross-tenant: evento de la organización A no puede actualizar recursos de la B, aunque el payload diga lo contrario.
- Test de outbox y reintento: fallo transitorio, reenvío, timeout, dead-letter y reintento manual.
- Contract test del esquema contra `packages/contracts/` y del adaptador con proveedor mock, sin red ni credenciales reales.
- Verificar en logs que no aparezcan cuerpo crudo, tokens, contraseñas ni CV.

## Checklist

- [ ] Contrato versionado y validado con Pydantic.
- [ ] Tenant resuelto desde configuración autenticada, no desde payload no confiable.
- [ ] Firma HMAC y tolerancia anti-replay implementadas y probadas.
- [ ] Deduplicación con llave única por organización y proveedor.
- [ ] Respuesta rápida y procesamiento en background con correlación.
- [ ] Reintentos, timeout, dead-letter y reintento manual documentados.
- [ ] Secretos fuera del repo y rotación probada.
- [ ] Payload sin CV ni datos personales innecesarios.
- [ ] Contratos, tests y `docs/DEVELOPMENT_WORKFLOW.md` actualizados.

## Referencias

- `TalentOS_SDD.md` secciones 11, 14.1, 15.1, 16.2 y 25.
- `TalentOS_ROADMAP.md` sección 3 (Fase 0) y sección 4 (CI verde).
- `AGENTS.md`, `docs/DEVELOPMENT_WORKFLOW.md`, `docs/ENVIRONMENTS.md`, `docs/decisions/`.
- Referencias oficiales citadas en `TalentOS_SDD.md` sección 26: FastAPI <https://fastapi.tiangolo.com/>, Pydantic <https://docs.pydantic.dev/>, PostgreSQL <https://www.postgresql.org/docs/>.
