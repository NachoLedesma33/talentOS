# Política de privacidad de TalentOS

Estado: demo/local. Esta política describe el tratamiento previsto por TalentOS y las garantías ya implementadas en el repositorio. No autoriza el uso de datos personales reales hasta cerrar los riesgos `RM-01`–`RM-05` de `docs/security-review.md`.

## 1. Responsable y alcance

TalentOS es una herramienta de reclutamiento asistido. Cada organización decide qué datos introduce y quién puede verlos dentro de su tenant. El acceso a la instancia local se entrega mediante credenciales de demostración; no se publica correo de contacto ni dato personal real en este repositorio.

La política cubre la aplicación web en `apps/web`, la API en `apps/api`, el worker y el almacenamiento privado definido en `docker-compose.yml`.

## 2. Datos tratados

- **Cuenta:** nombre, correo, contraseña hashada con bcrypt y rol por organización.
- **Organización:** nombre, slug, miembros y permisos.
- **Proceso de selección:** vacantes, candidatos sintéticos, etapas y evaluaciones con criterios, evidencias y brechas.
- **Documentos:** CV y archivos de apoyo, almacenados por clave UUID fuera de la base de datos transaccional.
- **Auditoría:** eventos de dominio, `correlation_id`, actor y timestamp; sin CV completo, tokens ni contraseñas.
- **Preferencias locales:** identificador de organización activa en `localStorage`; sin correos ni tokens en almacenamiento del navegador.

## 3. Finalidades

- Autenticar sesiones y aplicar permisos por rol y organización.
- Gestionar vacantes, candidatos, evaluaciones y aprobaciones humanas.
- Mostrar evidencia verificable con documento, página y fragmento.
- Registrar trazabilidad de acciones sensibles.
- Ejecutar la demo con proveedor `mock` y datos sintéticos, sin LLMs ni integraciones pagadas.

TalentOS no decide contrataciones de forma automática, no infiere atributos protegidos y no envía correos externos sin aprobación explícita.

## 4. Base de tratamiento

El tratamiento se limita a la relación contractual con la organización usuaria y a las instrucciones de sus administradores. Para datos de candidatos, la organización debe obtener consentimiento y definir procedencia y retención antes de usar la herramienta con información real. El formulario de registro y el alta de candidatos incorporarán este extremo en el lote 16-09 del roadmap.

## 5. Acceso y aislamiento

- Toda consulta se filtra por `organization_id` derivado de la sesión.
- La autorización se aplica en cada endpoint y operación de dominio.
- Roles y permisos se comprueban en servidor; el frontend no decide acceso.
- Las URLs de descarga son firmadas, están ligadas al tenant y caducan.
- Los documentos se guardan bajo claves UUID en storage privado.
- Los eventos de agente se purgan a los 30 días (`apps/api/app/agents/tasks.py`).

## 6. Conservación y eliminación

La demo usa datos sintéticos. La retención de candidatos reales y el borrado o exportación autoservicio quedan pendientes de los lotes 16-10 y 16-11 del roadmap; mientras tanto, no se introducen datos personales reales. La purga automática existente cubre solo eventos de agente. Los backups y su restauración están pendientes (`RM-05`).

## 7. Cookies y tecnologías locales

La sesión usa una cookie `HttpOnly`, `SameSite=lax` y `Secure` en producción. No hay cookies de analítica ni publicidad. `localStorage` guarda solo el identificador de organización activo; se elimina al cerrar sesión.

## 8. Proveedores y terceros

El modo demo usa `LLM_PROVIDER=mock` y no envía datos a proveedores externos. Si se configura un proveedor remoto, la organización debe revisar su contrato y la configuración de red antes de enviar contenido. Las integraciones externas requieren secretos cifrados por organización y aprobación humana para acciones salientes.

## 9. Seguridad

- Contraseñas hasheadas con bcrypt y límite de 72 bytes.
- Tokens de sesión opacos; solo se persiste su hash.
- CORS con origen explícito; verificación de `Origin` en métodos mutantes.
- Fernet por organización para secretos de integración.
- Validación de extensión, MIME, firma real, tamaño y páginas en archivos subidos.
- Defensas contra prompt injection, herramientas de agente acotadas y salidas validadas.
- Logs estructurados sin datos personales innecesarios.
- Escaneo de dependencias en CI.

Pendiente para producción: rate limit global HTTP, clave estable para URLs firmadas, HTTPS/HSTS verificados, exportación y borrado de candidatos, backup/restauración y escaneo de secretos en CI.

## 10. Derechos y solicitudes

La organización usuaria gestiona las solicitudes de acceso, corrección, exportación o eliminación a través de su administrador y del canal de contacto que defina para sus candidatos. TalentOS no expone un correlativo de usuarios: los identificadores públicos son UUID.

## 11. Cambios

Cualquier cambio de esta política se registra en el repositorio junto al lote del roadmap que lo motiva. Esta versión acompaña a la fase 16 y no sustituye la evaluación legal que cada organización debe realizar antes de tratar datos reales.
