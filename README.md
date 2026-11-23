# TalentOS

[![CI](https://github.com/NachoLedesma33/talentOS/actions/workflows/ci.yml/badge.svg)](https://github.com/NachoLedesma33/talentOS/actions/workflows/ci.yml)

Plataforma B2B de reclutamiento con API FastAPI, PostgreSQL, Redis y web Next.js. Estado: Fase 1 — fundación implementada.

## Inicio rápido

1. Clonar el repositorio y entrar en la raíz.
2. Copiar `.env.example` a `.env` (sin secretos reales; modo mock por defecto).
3. Levantar todo el entorno local:

```powershell
docker compose up -d
```

4. Verificar: web en `http://localhost:3000` y API en `http://localhost:8000/health`.
   `GET /ready` comprueba PostgreSQL y Redis; responde `503` si alguna dependencia falla.

Para detener el entorno y conservar los volúmenes:

```powershell
docker compose down
```

## Desarrollo local sin Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "apps/api[dev]"
cd apps/api
python -m pytest -q
uvicorn app.main:app --reload
```

## Alcance de esta fase

- Sin secretos versionados: `.env` queda fuera del repositorio.
- Modo mock sin credenciales de servicios pagos; usar solo datos sintéticos.
- El worker y los endpoints de negocio llegan en fases posteriores.
