# TalentOS — Entornos y configuración

Estado: Fase 0. Este documento fija entornos, variables y versiones reales del entorno de desarrollo. La estructura de carpetas, `.env.example` y Docker Compose se materializan en Fase 1; todavía no hay código de aplicación ni servicios levantados.

## Versiones detectadas en esta máquina

Medidas el 2026-11-23 con `python --version`, `node --version`, `npm --version`, `git --version` y `docker --version` desde la raíz del proyecto:

| Herramienta | Versión real |
|---|---|
| Python | 3.12.10 |
| Node.js | v24.22.1 |
| npm | 12.0.2 |
| Git | 2.40.0.windows.1 |
| Docker | 29.4.1, build 055a478 |
| Sistema operativo | Windows |

Consecuencias operativas: comandos Python se ejecutan con `python -m ...` (módulos del intérprete 3.12); scripts de shell se documentan en sintaxis compatible con PowerShell; los volúmenes y rutas de Docker Compose deben usar rutas relativas del repo para evitar diferencias de separador Windows/Linux. La compatibilidad efectiva de dependencias se confirma en Fase 1 con versiones fijadas en lockfiles y checks de CI; no se instala nada en Fase 0.

## Entornos (SDD 17.1)

| Entorno | Propósito | Datos | Proveedores y servicios |
|---|---|---|---|
| `local` | Desarrollo con Docker Compose. | Datos sintéticos; seed reproducible y reinicio de demo. | PostgreSQL y Redis locales, storage local de desarrollo, `LLM_PROVIDER=mock`. Sin credenciales pagas. |
| `test` | Ejecución automatizada de pytest, Vitest y Playwright. | Datos aislados por suite; base efímera; ningún dato personal real. | Proveedores mock obligatorios; adaptadores externos simulados; sin dependencia de red pagada. Incluye tests de aislamiento cross-tenant. |
| `staging` | Validación antes de producción; despliegue solo tras aprobación. | Datos ficticios/demo; datos reales solo con base legal y autorización explícita. | Integraciones en sandbox; migraciones aplicadas con plan de rollback; observabilidad activa. |
| `production` | Despliegue real. | Datos personales bajo política de retención, acceso por rol y separación de datos sintéticos. | Secretos en gestor, HTTPS, CORS restrictivo, backups probados, logs y alertas. Sin migraciones destructivas automáticas ni acciones externas sin aprobación. |

Regla transversal: ningún entorno toma secretos del repositorio. Si una configuración falta o es inválida, la aplicación debe fallar al iniciar con mensaje claro (RNF y SDD 17.2). La demo debe funcionar en `local` y `test` sin credenciales de servicios pagos.

Servicios locales previstos (SDD 17.3): `web`, `api`, `postgres`, `redis`, `worker`. Agregar storage compatible S3 solo cuando el flujo de archivos lo requiera en la fase correspondiente (Fase 4).

La cadena de CI es la del SDD 17.4: dependencias reproducibles → lint → typecheck → unitarios → integración → build frontend → build backend → escaneo de dependencias → validación de migraciones → deploy a staging tras aprobación. Detalle y comandos en `AGENTS.md` y `docs/DEVELOPMENT_WORKFLOW.md`.

## Variables de entorno (SDD 17.2)

Bloque a crear textualmente en `.env.example` durante Fase 1. Campos vacíos se dejan vacíos: se completan en el entorno correspondiente, nunca en el repositorio. El valor de `DATABASE_URL` es el ejemplo local documentado en el SDD, no una credencial real.

```env
APP_ENV=local
APP_NAME=TalentOS
API_BASE_URL=http://localhost:8000
WEB_BASE_URL=http://localhost:3000

DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/talentos
REDIS_URL=redis://localhost:6379/0

AUTH_SECRET=
STORAGE_ENDPOINT=
STORAGE_BUCKET=
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=

LLM_PROVIDER=mock
LLM_API_KEY=
LLM_MODEL=
LLM_BASE_URL=

LOG_LEVEL=INFO
```

| Variable | Uso |
|---|---|
| `APP_ENV`, `APP_NAME` | Identificación del entorno y de la aplicación en logs. |
| `API_BASE_URL`, `WEB_BASE_URL` | Orígenes locales de API y web; base de CORS y links. |
| `DATABASE_URL`, `REDIS_URL` | Conexiones a PostgreSQL y Redis; la URL de DB incluye driver `psycopg`. |
| `AUTH_SECRET` | Firma de sesiones/tokens; obligatorio fuera de modo mock. |
| `STORAGE_*` | Configuración de storage privado compatible S3; se habilita con el flujo de documentos. |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL` | Selección de proveedor; `mock` es el default de desarrollo y test. |
| `LOG_LEVEL` | Nivel de logs estructurados; sin CVs, tokens ni datos personales en los mensajes. |

## Estado actual de archivos de entorno

No existe `.env` en esta máquina. Tampoco existe todavía `.env.example`: se crea en Fase 1. `.env` nunca debe versionarse; el repo debe ignorarlo. Cualquier clave real que se haya usado durante desarrollo queda fuera de este documento y de cualquier fixture, log o commit.

Cuando se creen, la validación de configuración debe comprobar al arranque: variables obligatorias presentes, `APP_ENV` dentro de los cuatro valores documentados, `LLM_PROVIDER=mock` en `test`, y URLs sintácticamente válidas; ante error, mensaje explícito sin imprimir valores secretos.
