# TalentOS

Plataforma B2B de reclutamiento con API FastAPI, PostgreSQL y Redis. Estado: Fase 1 en progreso.

## Instalación local

1. Clonar el repositorio y entrar en la raíz.
2. Copiar `.env.example` a `.env` (sin secretos reales; modo mock por defecto).
3. Levantar infraestructura: `docker compose up -d postgres redis`.
4. Crear entorno e instalar dependencias:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "apps/api[dev]"
```

5. Ejecutar tests: `cd apps/api && python -m pytest -q`.
6. Arrancar la API: `cd apps/api && uvicorn app.main:app --reload`.

Endpoints disponibles: `GET /health` y `GET /ready`.

Nota: use datos sintéticos, sin credenciales reales; los proveedores externos funcionan en modo `mock`.
