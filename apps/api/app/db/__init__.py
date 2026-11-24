"""Persistencia de TalentOS: metadata base, sesión y dependencia de FastAPI."""

from __future__ import annotations

import sys

# Registro de metadata del runtime. Se evita el import incondicional: cuando
# `app.agents.models` se importa primero, ya está en sys.modules (parcial) y
# un re-import aquí provocaría un ciclo con `app.db.base`. Si `app.db` se
# importa primero, este bloque registra los modelos nuevos en Base.metadata.
if "app.agents.models" not in sys.modules:
    from app.agents.models import (  # noqa: E402, F401
        AgentCheckpoint,
        AgentEvent,
        AgentRun,
        Approval,
    )

# Mismo guard para entidades de entrevistas: el módulo importa `app.db.base`.
if "app.interviews.models" not in sys.modules:
    from app.interviews.models import (  # noqa: E402, F401
        InterviewFeedback,
        InterviewGuide,
        InterviewGuideRevision,
        InterviewQuestion,
    )

# Fase 8: registro del motor de automatización con el mismo anti-ciclo.
if "app.automation.models" not in sys.modules:
    from app.automation.models import (  # noqa: E402, F401
        Automation,
        AutomationApproval,
        AutomationRun,
        AutomationRunEvent,
        AutomationVersion,
    )
